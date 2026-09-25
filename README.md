# HRIS & Payroll Dashboard

Platform **HRIS (Human Resource Information System) & Payroll multi-perusahaan** berbasis web. Satu instalasi dapat melayani banyak perusahaan (tenant) dengan data yang terisolasi penuh, hak akses berbasis peran (RBAC), alur persetujuan yang dapat dikonfigurasi, serta modul payroll yang mengikuti aturan perpajakan Indonesia (PPh 21 metode TER).

---

## 1. Overview Project

HRIS & Payroll Dashboard Dashboard Dashboard JAYA123 membantu tim HR dan Finance mengelola siklus hidup karyawan dari satu tempat:

| Area | Fitur Utama |
|------|-------------|
| **Multi-perusahaan** | Satu akun dapat memiliki peran berbeda di beberapa perusahaan; pemilih perusahaan aktif di topbar; setiap query dibatasi `company_id` di sisi server. |
| **Autentikasi & Hak Akses** | Login email/kata sandi (JWT access + refresh token), penguncian akun setelah percobaan gagal, peran & permission granular (`resource:action`), super admin lintas perusahaan. |
| **Master Data Organisasi** | Cabang, lokasi kerja, departemen, divisi, jabatan, grade/level, cost center, proyek, status kepegawaian, tipe kontrak, tipe sertifikasi, tipe dokumen. |
| **Data Karyawan** | Profil karyawan lengkap, kontrak kerja (dengan **renewal/perpanjangan**), sertifikasi, arsip dokumen (disimpan di object storage), **impor massal dari Excel**. |
| **Kalender Masa Berlaku & Pengingat** | Dashboard kontrak/sertifikasi/dokumen yang akan kedaluwarsa; **email reminder otomatis** via SMTP perusahaan yang dijadwalkan oleh APScheduler (zona Asia/Jakarta). |
| **Payroll** | Komponen gaji (earning/deduction), konfigurasi BPJS & PPh 21 TER, gaji per karyawan, **payroll run** dengan alur draft → submit → approve → paid, penyesuaian per item, **slip gaji PDF**, file transfer bank, dan laporan statutori (export Excel). |
| **Konfigurasi & Audit** | Aktivasi modul per perusahaan, kebijakan (policy) perusahaan, alur persetujuan bertingkat, pengaturan email, **audit log** untuk setiap perubahan data. |

Bahasa antarmuka: **Bahasa Indonesia**.

### Akun Demo

Aplikasi otomatis melakukan *seed* data demo saat backend pertama kali dijalankan (2 perusahaan: **NEP** dan **KBS**). Kata sandi semua akun demo: `Hris#2026`

| Peran | Email |
|-------|-------|
| Super Admin (semua perusahaan) | `superadmin@hris.id` |
| HR Admin (NEP) | `hr.admin@nep.co.id` |
| HR Manager (NEP) | `hr.manager@nep.co.id` |
| Finance (NEP) | `finance@nep.co.id` |
| Karyawan (NEP) | `karyawan@nep.co.id` |
| HR Multi-perusahaan (NEP + KBS) | `hr.multi@hris.id` |
| HR Admin (KBS) | `hr.admin@kbs.co.id` |

---

## 2. Tech Stack

Ringkasan: **React + Nginx** (frontend) · **FastAPI** (backend) · **MariaDB** (database) · **phpMyAdmin** (GUI database) · **Cloudflare R2** (penyimpanan dokumen) · **Docker** di **Coolify** (deployment, 1 repo dengan base directory `/backend` dan `/frontend`).

### Frontend
| Komponen | Teknologi |
|----------|-----------|
| Framework | **React 19** (Create React App + CRACO) |
| Routing | React Router v7 |
| UI Kit | **shadcn/ui** (Radix UI primitives) + **Tailwind CSS** |
| Ikon | lucide-react |
| HTTP Client | Axios (interceptor Bearer token & auto-logout 401); base URL `/api` relatif di produksi |
| Form & Validasi | react-hook-form + zod |
| Notifikasi | sonner (toast) |
| Grafik | recharts |
| Tanggal / Format | dayjs, date-fns, `Intl.NumberFormat` (IDR) |
| Web server produksi | **Nginx 1.27** (alpine) — serve static build + reverse-proxy `/api` → backend |
| Build image | Multi-stage `node:20-alpine` → `nginx:1.27-alpine` (`frontend/Dockerfile`) |

### Backend
| Komponen | Teknologi |
|----------|-----------|
| Framework | **FastAPI 0.110** (Python 3.11, async) |
| Server | Uvicorn (image `python:3.11-slim`, `backend/Dockerfile`, port 8001) |
| Validasi | Pydantic v2 |
| Database driver | **SQLAlchemy 2.0 Core (async)** + **asyncmy** → MariaDB; adapter API bergaya dokumen di `app/core/db.py` |
| Object storage | **boto3** (S3 compatible) → **Cloudflare R2** |
| Autentikasi | PyJWT (HS256) + bcrypt |
| Penjadwal | APScheduler (job pengingat per jam, zona Asia/Jakarta) |
| PDF | ReportLab (slip gaji) |
| Excel | openpyxl (impor karyawan, export laporan, file bank) |
| Email | smtplib + SSL/STARTTLS (SMTP per perusahaan) |

### Infrastruktur & Deployment
| Komponen | Teknologi |
|----------|-----------|
| Platform | **Coolify** (self-hosted PaaS) di VPS, Docker build strategy |
| Database | **MariaDB 11.x** (resource Database Coolify) |
| GUI Database | **phpMyAdmin 5** (resource Service Coolify) |
| Penyimpanan berkas | **Cloudflare R2** (bucket S3-compatible) |
| Orkestrasi lokal | `docker-compose.yml` di root (mariadb, phpmyadmin, backend, frontend) |
| Reverse proxy publik | Traefik/Caddy bawaan Coolify (TLS otomatis) → Nginx frontend → FastAPI |

### Database
- **MariaDB 10.11+/11.x** — satu database, setiap entitas menjadi tabel dengan kolom `company_id` pada tabel tenant. Skema (tabel, kolom, indeks, unique) dibuat/diperbarui otomatis saat startup oleh `ensure_indexes()` di `backend/app/core/db.py` — tidak perlu migrasi manual; kolom baru yang ditambahkan ke katalog akan di-`ALTER TABLE` otomatis.
- Lapisan akses data (`app/core/db.py`) mengekspos API bergaya dokumen (`find_one`, `update_one({"$set": ...})`, dll.) yang diterjemahkan ke SQL, sehingga logika bisnis router tidak berubah. Objek bertingkat (mis. `payroll_items.earnings`, `payroll_runs.history`) disimpan sebagai kolom **JSON**; key yang tidak punya kolom masuk ke kolom `extra` (JSON).
- Tabel utama: `companies`, `users`, `roles`, `employees`, `employee_contracts`, `employee_certifications`, `documents`, `payroll_components`, `employee_salaries`, `payroll_runs`, `approval_workflows`, `config_overrides`, `smtp_settings`, `audit_logs`, dan koleksi master data (`branches`, `departments`, `positions`, dll.).

### Autentikasi
- **JWT (HS256)** — access token (default 12 jam) & refresh token (default 14 hari), payload menyimpan `sub` (user id) dan `active_company_id`.
- Kata sandi di-hash dengan **bcrypt**.
- **RBAC**: permission berbentuk `resource:action` (mis. `employees:create`), diperiksa di server melalui dependency `require_permission()`; modul harus aktif untuk perusahaan (`module_key`).
- Perlindungan brute-force: penguncian sementara setelah `LOGIN_MAX_ATTEMPTS` gagal.

### Storage
- **Cloudflare R2 (S3 compatible, via boto3)** — semua file dokumen karyawan (PDF, gambar, Office) disimpan di bucket R2, **bukan** di disk server. Path objek: `{R2_PREFIX}/companies/{company_id}/documents/{file_id}.{ext}`. Konfigurasi lewat env `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET_NAME` (+ opsional `R2_ENDPOINT_URL`).
- Metadata file (nama, ukuran, MIME, path) disimpan di tabel MariaDB `documents`.
- Slip gaji PDF & file Excel dihasilkan on-the-fly (streaming), tidak disimpan.

---

## 3. Folder Structure

```
payroll/
├── backend/                       # FastAPI application
│   ├── server.py                  # Entry point: FastAPI app, CORS, router registration, lifecycle (startup seed/index/scheduler)
│   ├── requirements.txt           # Dependensi Python (pip)
│   ├── pytest.ini                 # Konfigurasi pytest (xdist, 2 worker)
│   ├── test_core.py               # Smoke test core flow (login, tenant scope, RBAC)
│   ├── .env                       # DATABASE_URL, CORS_ORIGINS, JWT_SECRET, R2_* (tidak di-commit)
│   └── app/
│       ├── schemas.py             # Pydantic model request/response (LoginRequest, CompanyCreate, PayrollRunCreate, ...)
│       ├── masters.py             # Definisi generik master data (resource, field, label, validasi)
│       ├── seed.py                # Seed data demo: perusahaan, user, roles, master data, karyawan, payroll
│       ├── core/                  # Lapisan infrastruktur & domain logic (tidak bergantung pada HTTP)
│       │   ├── config.py          # Settings dari environment (.env)
│       │   ├── db.py              # Koneksi Motor, ensure_indexes, helper id/audit_fields
│       │   ├── repo.py            # TenantRepository: CRUD yang selalu ter-scope company_id
│       │   ├── security.py        # bcrypt hash/verify, pembuatan & verifikasi JWT
│       │   ├── deps.py            # FastAPI dependencies: get_auth, require_permission, require_super_admin
│       │   ├── rbac.py            # Katalog peran, permission, dan default permission per role
│       │   ├── policy.py          # Kebijakan perusahaan (password, dokumen, dsb.)
│       │   ├── audit.py           # Pencatatan audit log (who/what/when/before/after)
│       │   ├── storage.py         # Klien object storage (put/get/delete) untuk dokumen
│       │   ├── demo_files.py      # Pembuat file demo (PDF/gambar) untuk seed dokumen
│       │   ├── expiry.py          # Perhitungan masa berlaku & kategori urgensi
│       │   ├── scheduler.py       # APScheduler: job pengingat per jam (Asia/Jakarta)
│       │   ├── mailer.py          # Pengiriman SMTP (konfigurasi per perusahaan, password write-only)
│       │   ├── reminder_mail.py   # Template & logika email pengingat kedaluwarsa
│       │   ├── excel.py           # Parser/validator impor karyawan dari Excel & template
│       │   ├── payroll.py         # Kalkulasi gaji: komponen, BPJS, prorata, pembulatan
│       │   ├── ter.py             # Tabel & fungsi PPh 21 metode TER (Tarif Efektif Rata-rata)
│       │   ├── payroll_service.py # Orkestrasi payroll run: hitung item, rekap, status transisi
│       │   └── pdf.py             # Generator slip gaji PDF (ReportLab)
│       └── routers/               # Endpoint HTTP, satu file per domain (semua di bawah prefix /api)
│           ├── auth.py            # /auth: login, refresh, switch-company, change-password, me
│           ├── companies.py       # /companies: profil, settings, aktivasi modul
│           ├── users.py           # /users & /roles: manajemen pengguna & peran
│           ├── master.py          # /master/{resource}: CRUD generik master data
│           ├── policies.py        # /policies: kebijakan perusahaan
│           ├── approvals.py       # /approval-workflows: alur persetujuan bertingkat
│           ├── employees.py       # /employees: CRUD karyawan, impor Excel, template
│           ├── contracts.py       # /employees/{id}/contracts: kontrak kerja & renewal
│           ├── certifications.py  # /employees/{id}/certifications: sertifikasi
│           ├── documents.py       # /documents: upload/download/preview via object storage
│           ├── reminders.py       # /reminders: kalender masa berlaku, kirim pengingat manual
│           ├── settings_mail.py   # /settings/mail: konfigurasi SMTP & tes kirim
│           ├── payroll.py         # /payroll: komponen, config, salaries, runs, payslip, bank file, laporan
│           ├── dashboard.py       # /dashboard: ringkasan, tindak lanjut, kelengkapan setup
│           └── audit_logs.py      # /audit-logs: riwayat perubahan
│
├── frontend/                      # React application
│   ├── package.json               # Dependensi JS (yarn)
│   ├── craco.config.js            # Override CRA (alias @/, hot reload)
│   ├── tailwind.config.js         # Tema Tailwind (token warna, radius, font)
│   ├── components.json            # Konfigurasi shadcn/ui
│   ├── jsconfig.json              # Alias path `@/*` -> `src/*`
│   ├── .env                       # REACT_APP_BACKEND_URL (tidak di-commit)
│   ├── public/                    # index.html & aset statis
│   └── src/
│       ├── index.js               # Bootstrap React (StrictMode, root render)
│       ├── index.css              # Tailwind base + CSS variables tema (shadcn)
│       ├── App.js                 # Router utama, guard autentikasi, AppShell
│       ├── App.css                # Style global tambahan
│       ├── lib/                   # Utilitas non-visual
│       │   ├── api.js             # Instance Axios (baseURL /api, interceptor token & 401)
│       │   ├── auth.jsx           # AuthProvider/useAuth: sesi, user, perusahaan aktif, permission
│       │   ├── nav.js             # Definisi menu sidebar (grup, ikon, permission)
│       │   ├── masterConfig.js    # Konfigurasi kolom/form untuk halaman master data generik
│       │   ├── format.js          # Formatter tanggal, uang (IDR), label status
│       │   ├── download.js        # Helper unduh blob (PDF/Excel) dari API
│       │   └── utils.js           # cn() (clsx + tailwind-merge)
│       ├── hooks/
│       │   └── use-toast.js       # Hook toast
│       ├── constants/testIds/     # Konstanta data-testid untuk pengujian E2E
│       ├── components/
│       │   ├── ui/                # Komponen shadcn/ui (button, dialog, table, ...) — jangan diedit manual
│       │   ├── common/            # Komponen reusable: DataTable, FormDialog, DetailDrawer, StatusBadge, Money, EmptyState, DocumentPreview
│       │   ├── layout/            # AppShell, Sidebar, Topbar, CompanySwitcher
│       │   └── payroll/           # Komponen spesifik payroll (ContractRenewDialog, ...)
│       └── pages/                 # Satu file per halaman/route
│           ├── LoginPage.jsx, DashboardPage.jsx, CompanyProfilePage.jsx
│           ├── SetupHubPage.jsx, MasterDataPage.jsx, ModuleActivationPage.jsx
│           ├── PoliciesPage.jsx, ApprovalWorkflowPage.jsx, UsersPage.jsx, RolesPage.jsx
│           ├── EmployeesPage.jsx, EmployeeDetailPage.jsx, EmployeeImportPage.jsx
│           ├── DocumentsPage.jsx, ExpiryCalendarPage.jsx, MailSettingsPage.jsx
│           ├── PayrollRunsPage.jsx, PayrollRunDetailPage.jsx, PayrollComponentsPage.jsx
│           ├── EmployeeSalariesPage.jsx, PayrollConfigPage.jsx, MyPayslipsPage.jsx
│           └── AuditLogPage.jsx, SettingsPage.jsx, ProfilePage.jsx, NotFoundPage.jsx
│
├── tests/                         # Pengujian otomatis (pytest)
├── test_reports/                  # Laporan hasil pengujian per iterasi (JSON)
├── backend_test.py                # Suite pengujian API backend end-to-end
├── regression_test.py             # Pengujian regresi fitur utama
├── memory/                        # Catatan agen: PRD, kredensial uji
├── plan.md                        # Rencana pengembangan per fase & status
├── design_guidelines.md           # Panduan desain UI (warna, tipografi, komponen)
└── README.md
```

---

## 4. Data Flow

### 4.1 Alur Request Umum

```
┌──────────────┐   1. Axios request      ┌─────────────────────┐   4. Motor query       ┌──────────────┐
│  React Page  │ ──────────────────────▶ │  FastAPI Router     │ ─────────────────────▶ │   MariaDB    │
│  (pages/*)   │   Authorization: Bearer │  (/api/...)         │   {company_id: ...}    │              │
│              │ ◀────────────────────── │                     │ ◀───────────────────── │              │
└──────────────┘   6. JSON response      └─────────────────────┘   5. documents         └──────────────┘
                                            │  2. Depends(get_auth)
                                            │     - verifikasi JWT
                                            │     - muat user + perusahaan aktif
                                            │     - hitung effective permissions
                                            │  3. require_permission("employees","read")
                                            │     - cek modul aktif & permission
                                            ▼
                                     TenantRepository("employees", company_id)
                                     (setiap query otomatis di-scope ke company_id)
```

1. **Frontend** memanggil `api.get('/employees')` melalui instance Axios di `lib/api.js`. Interceptor menambahkan header `Authorization: Bearer <access_token>` dari `localStorage`.
2. **Ingress** meneruskan semua path `/api/*` ke backend FastAPI (port 8001); path lain ke frontend (port 3000).
3. **Router** FastAPI menerima request. Dependency `get_auth` memverifikasi JWT, memuat user, menentukan `active_company_id`, dan menghitung permission efektif (gabungan role per perusahaan + super admin).
4. `require_permission(resource, action, module_key)` menolak dengan `403` jika permission tidak ada atau modul belum diaktifkan perusahaan.
5. Handler memakai **`TenantRepository`** — semua `find/insert/update` otomatis menambahkan filter `company_id`, sehingga data lintas perusahaan tidak pernah bocor.
6. Perubahan data dicatat ke `audit_logs` (`core/audit.py`) dengan snapshot sebelum/sesudah.
7. Respons JSON dikembalikan; frontend memperbarui state dan menampilkan toast (sonner).
8. Jika backend membalas `401`, interceptor Axios memanggil handler logout → pengguna diarahkan ke `/login`.

### 4.2 Alur Autentikasi

```
LoginPage ──POST /api/auth/login──▶ auth.py ──▶ verifikasi bcrypt ──▶ JWT access+refresh
    │                                                  │
    └── simpan token di localStorage ◀─────────────────┘
AuthProvider ──GET /api/auth/me──▶ user, daftar perusahaan, permission, modul aktif
CompanySwitcher ──POST /api/auth/switch-company──▶ token baru dengan active_company_id berbeda
```

### 4.3 Alur Upload Dokumen

```
DocumentsPage ──multipart POST /api/documents──▶ documents.py
                                                    ├─▶ validasi ukuran/MIME (policy)
                                                    ├─▶ storage.put_object() ──▶ Object Storage
                                                    └─▶ simpan metadata ──▶ MariaDB `documents`
Preview/Download ──GET /api/documents/{id}/download──▶ storage.get_object() ──▶ stream ke browser
```

### 4.4 Alur Payroll Run

```
PayrollRunsPage ──POST /api/payroll/runs {period}──▶ payroll_service.create_run()
   ├─▶ ambil employee_salaries + payroll_components + config (BPJS, PTKP)
   ├─▶ payroll.py: hitung earning/deduction, BPJS TK/KS
   ├─▶ ter.py: PPh 21 metode TER berdasarkan status PTKP
   └─▶ simpan payroll_runs (items[], totals, status="draft")

Status: draft ──submit──▶ pending_approval ──approve──▶ approved ──mark-paid──▶ paid
                                            └──reject──▶ draft

Output: GET .../payslip (PDF via ReportLab) · GET .../bank-file (Excel) · GET .../statutory-report/export
```

### 4.5 Alur Pengingat Otomatis

```
APScheduler (setiap jam, Asia/Jakarta)
   └─▶ scheduler.py ──▶ untuk setiap perusahaan dengan jadwal cocok:
         ├─▶ expiry.py: cari kontrak/sertifikasi/dokumen yang akan kedaluwarsa (H-30/H-14/H-7)
         ├─▶ reminder_mail.py: susun email HTML
         └─▶ mailer.py: kirim via SMTP perusahaan (smtp_settings) ──▶ catat hasil di reminders log
```

---

## 5. Coding Conventions

### 5.1 Umum
- **Bahasa UI & pesan error untuk pengguna: Bahasa Indonesia.** Nama variabel, fungsi, file, dan komentar teknis: **Bahasa Inggris**.
- Semua endpoint backend **wajib** berada di bawah prefix `/api` (routing ingress).
- Konfigurasi (URL, secret, nama DB) **hanya** dari environment variable (`.env`) — tidak ada hardcode.
- ID dokumen memakai **UUID v4 string** (`new_id()`), bukan `ObjectId`, agar aman diserialisasi ke JSON.
- Timestamp disimpan sebagai ISO-8601 UTC string (`created_at`, `updated_at`, `created_by`, `updated_by` via `audit_fields()`).
- Soft delete: field `status: "deleted"`; `TenantRepository.list()` otomatis mengecualikannya.

### 5.2 Backend (Python / FastAPI)
| Aspek | Konvensi |
|-------|----------|
| Nama file | `snake_case.py`; satu router per domain di `app/routers/`, logika non-HTTP di `app/core/`. |
| Fungsi & variabel | `snake_case`; handler async (`async def list_employees`). |
| Class | `PascalCase` (`TenantRepository`, `EmployeeCreate`). |
| Konstanta | `UPPER_SNAKE_CASE` (`DEMO_PASSWORD`, `MIME_TYPES`). |
| Skema | Pydantic v2 di `schemas.py`; pola `XxxCreate` / `XxxUpdate` (semua field Optional) / `XxxOut`. |
| Router | `router = APIRouter(prefix="/employees", tags=["Karyawan"])`; didaftarkan ke `api` router di `server.py`. |
| Otorisasi | Selalu `Depends(require_permission("resource", "action", module_key="..."))` — jangan cek di frontend saja. |
| Akses data | Wajib lewat `TenantRepository`; hindari `get_db()[coll].find()` langsung kecuali koleksi global (`users`, `companies`). |
| Error | `raise HTTPException(status.HTTP_4XX, "Pesan dalam Bahasa Indonesia")`; validation error di-*flatten* oleh handler global di `server.py`. |
| Logging | `logging.getLogger("hris.<modul>")`; jangan log kata sandi/token/isi file. |
| Import | Absolut dari package `app` (`from app.core.db import get_db`) di router; relatif (`from .db import ...`) di dalam `core/`. |
| Format | `black` (line length default) + `isort`; lint `flake8`. |
| Dependensi | Tambah via `pip install <pkg>` lalu `pip freeze > requirements.txt`. |

### 5.3 Frontend (React / JavaScript)
| Aspek | Konvensi |
|-------|----------|
| Nama file komponen/halaman | `PascalCase.jsx` (`EmployeeDetailPage.jsx`, `DataTable.jsx`). Halaman diakhiri `Page`. |
| Nama file utilitas/hook | `camelCase.js` (`format.js`, `use-toast.js` mengikuti konvensi shadcn). |
| Komponen | Function component + hooks; `export default` untuk halaman, named export untuk komponen reusable. |
| Variabel/fungsi | `camelCase`; handler event diawali `handle` (`handleSubmit`); boolean diawali `is/has/can`. |
| Konstanta | `UPPER_SNAKE_CASE` (`TOKEN_KEY`, `API`). |
| Import path | Alias `@/` untuk `src/` (`import { Button } from "@/components/ui/button"`). |
| Styling | Tailwind utility classes; gabungkan class dengan `cn()`; token warna dari CSS variables di `index.css` — hindari warna hex inline. |
| UI primitives | Gunakan komponen `components/ui/*` (shadcn). Komponen di folder ini di-generate — jangan diedit manual, buat wrapper di `components/common/`. |
| Data fetching | Selalu via `api` dari `lib/api.js` (bukan `fetch` langsung); tangani state `loading`, `empty` (`EmptyState`), dan `error` (toast). |
| Form | `react-hook-form` + `zod` untuk validasi; dialog form memakai `FormDialog`. |
| Uang & tanggal | `formatMoney()`/`<Money />` untuk IDR, `formatDate()` dari `lib/format.js`. |
| Testing hooks | Setiap elemen interaktif (tombol, input, baris tabel, menu) memiliki atribut `data-testid` deskriptif dalam `kebab-case` (`employee-save-button`). |
| Routing | Route didefinisikan di `App.js`; menu sidebar di `lib/nav.js` dengan `permission` yang dibutuhkan agar tersembunyi jika tidak berhak. |
| Dependensi | Tambah via `yarn add <pkg>` (jangan `npm`). |

### 5.4 Git
- Branch utama: `main`. Fitur dikerjakan di branch terpisah lalu di-merge ke `main`.
- Pesan commit deskriptif, dalam Bahasa Indonesia atau Inggris, diawali ringkasan singkat.
- File `.env`, `node_modules/`, `__pycache__/`, `uploads/`, dan artefak build tidak di-commit.

---

## Menjalankan Secara Lokal

```bash
# Backend
cd backend
pip install -r requirements.txt
cp .env.example .env   # isi DATABASE_URL (MariaDB), JWT_SECRET, R2_*
uvicorn server:app --host 0.0.0.0 --port 8001 --reload

# Frontend
cd frontend
yarn install
# .env: REACT_APP_BACKEND_URL=http://localhost:8001
yarn start
```

Buka `http://localhost:3000`, login dengan salah satu akun demo di atas. Dokumentasi API interaktif tersedia di `http://localhost:8001/docs`.

### Environment Variables

| Variabel | Sisi | Keterangan |
|----------|------|------------|
| `DATABASE_URL` | backend | Connection string MariaDB, mis. `mysql://user:pass@host:3306/hris_payroll` (alternatif: `DB_HOST/DB_PORT/DB_USER/DB_PASSWORD/DB_NAME`) |
| `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET_NAME`, `R2_ENDPOINT_URL` | backend | Kredensial Cloudflare R2 untuk penyimpanan dokumen |
| `AUTO_SEED` | backend | Default `false`: startup tidak mengubah data bisnis. `true` = isi data demo saat startup (idempoten), hanya untuk demo/lokal. Seed eksplisit: `python -m app.seed` |
| `CORS_ORIGINS` | backend | Daftar origin dipisah koma, atau `*` |
| `JWT_SECRET` | backend | Secret penandatanganan JWT (wajib diganti di produksi) |
| `ACCESS_TOKEN_EXPIRE_MINUTES` / `REFRESH_TOKEN_EXPIRE_DAYS` | backend | Umur token (default 720 / 14) |
| `LOGIN_MAX_ATTEMPTS` / `LOGIN_LOCK_MINUTES` | backend | Proteksi brute-force (default 8 / 10) |
| `MAX_UPLOAD_MB` | backend | Batas ukuran upload dokumen (default 15) |
| `REACT_APP_BACKEND_URL` | frontend (build-time) | URL dasar backend tanpa `/api`. **Kosongkan di produksi** agar frontend memanggil `/api` relatif yang di-proxy Nginx ke backend |
| `BACKEND_UPSTREAM` | frontend (runtime, Nginx) | Alamat internal backend untuk proxy `/api`, default `http://backend:8001` |

---

## Deploy ke Coolify (Docker)

Repo ini **satu repo** dengan dua base directory yang masing-masing punya `Dockerfile`:

| Service | Tipe Coolify | Base directory | Port internal | Catatan |
|---------|--------------|----------------|---------------|---------|
| `mariadb` | Database (MariaDB 11) | — | 3306 | dibuat dari menu Databases |
| `phpmyadmin` | Service (phpMyAdmin) | — | 80 | `PMA_HOST` = hostname internal MariaDB |
| `backend` | Application → Dockerfile | `/backend` | **8001** | FastAPI |
| `frontend` | Application → Dockerfile | `/frontend` | **80** | Nginx: React + proxy `/api` → backend |

### 1. MariaDB
Buat resource **MariaDB** di project. Catat *internal URL*-nya, bentuknya
`mysql://USER:PASS@<uuid-container>:3306/<db>`. Tabel & indeks dibuat otomatis oleh backend saat start (tidak perlu SQL manual).

### 2. Backend (`Backend-Payroll`)
- Build Pack: **Dockerfile**, Base Directory: `/backend`, Port exposes: `8001`.
- Domain: opsional (tidak wajib, karena diakses lewat proxy frontend).
- Environment variables:

```env
DATABASE_URL=mysql://USER:PASS@<host-internal-mariadb>:3306/<db>
JWT_SECRET=<acak panjang>
CORS_ORIGINS=https://hris.akuntakita.com
AUTO_SEED=false
MAX_UPLOAD_MB=15
R2_ACCOUNT_ID=<cloudflare account id>
R2_ACCESS_KEY_ID=<r2 access key>
R2_SECRET_ACCESS_KEY=<r2 secret>
R2_BUCKET_NAME=media-akunkita
R2_ENDPOINT_URL=https://<account-id>.r2.cloudflarestorage.com
R2_PUBLIC_BASE_URL=https://pub-xxxx.r2.dev   # opsional, URL publik bucket
```

### 3. Frontend (`Frontend-Payroll`)
- Build Pack: **Dockerfile**, Base Directory: `/frontend`, Port exposes: `80`.
- Domain: `https://hris.akuntakita.com`.
- Build arg `REACT_APP_BACKEND_URL` **dibiarkan kosong** (frontend memanggil `/api` relatif).
- Environment variable runtime:

```env
BACKEND_UPSTREAM=http://<nama-container-backend>:8001
```

Nama container backend dapat dilihat di Coolify → Backend-Payroll → *Advanced / Network* (biasanya `<uuid>`; bisa diberi **Custom Docker Container Name**, mis. `hris-backend`, agar mudah). Backend & frontend harus berada di *destination/network* yang sama, atau aktifkan **"Connect To Predefined Network"** pada keduanya.

### 4. phpMyAdmin
Service phpMyAdmin dari katalog Coolify; set `PMA_HOST` ke hostname internal MariaDB dan beri domain (mis. `db.hris.akuntakita.com`). Login dengan user/password MariaDB.

### Alternatif: satu resource Docker Compose
Root repo menyediakan `docker-compose.yml` (4 service sekaligus). Di Coolify pilih Build Pack **Docker Compose**, isi env sesuai `.env.example` di root. Untuk lokal:

```bash
cp .env.example .env   # isi password & JWT_SECRET
docker compose up -d --build
# app: http://localhost:3000  |  phpMyAdmin: http://localhost:8080
```

### Health check
- Backend: `GET /api/health` → `{"status":"healthy","database":"mariadb:connected"}`
- Frontend (Nginx): `GET /healthz` → `ok`
