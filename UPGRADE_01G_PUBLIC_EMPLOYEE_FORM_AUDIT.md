# UPGRADE 01G — Public Employee Form — AUDIT & DESIGN

- Environment: **STAGING only** · Branch aktif: `feature/upgrade-01f-data-completeness` (belum ada branch 01G; dibuat saat implementasi disetujui)
- Tahap: **AUDIT & DESIGN ONLY** — tidak ada kode, schema, migration, atau data yang diubah.
- Status 01B/01C/01D/01F: LOCKED · 01E: stabil.
- Production Changed: **NO** · Push/PR/merge/deploy: **TIDAK ADA**

Semua temuan di bawah hasil inspeksi kode + query database **read-only** (sesi `READ ONLY`, rollback).

---

## 0. Ringkasan Eksekutif

| Topik | Temuan | Konsekuensi 01G |
|---|---|---|
| Public link / token | **Belum ada** mekanisme token publik, invitation, magic link, atau reset password | Dibangun baru (opaque token, hash-only) |
| Route publik | Hanya `GET /api/public/branding[/{asset}]` (read-only, tanpa tenant) | Router publik baru `/api/public/employee-form/*` |
| Auth | JWT Bearer (header), tanpa cookie, tanpa CSRF; `AuthContext` + RBAC | Sesi publik **terpisah** dari login (audience/secret berbeda, tanpa permission internal) |
| Rate limit | Hanya lockout login per user (`users.failed_login_attempts`, `locked_until`; 8x → 10 menit) | Counter gagal per-link di DB + limiter per-IP ringan |
| Audit | `build_audit_entry`/`log_action`; ip + user_agent; `mask_for_audit` otomatis | Reuse; event publik dengan `user_id=NULL`, tanpa nilai sensitif |
| Masking | `app/core/sensitive.py` — NIK, NPWP, rekening, BPJS KES/TK (4 digit terakhir) | Reuse `mask_value` untuk prefill |
| Storage | S3/R2 tenant-prefixed, download via proxy API (bukan URL publik) | Reuse `put_object/get_object`, prefix baru untuk lampiran submission |
| Upload | Validasi ekstensi + ukuran per `document_types`; cek signature hanya untuk foto (`read_image_upload`) | Tambah cek signature PDF/JPG/PNG untuk upload publik |
| Email/WA | SMTP per-tenant ada (`smtp_settings`, `core/mailer.py`), default belum dikonfigurasi; **WhatsApp tidak ada** | 01G: HR **copy link** saja; email opsional nanti |
| 01F | `evaluate(emp, ctx)` **pure** (tanpa tulis snapshot) | Bisa hitung "perkiraan" draft tanpa menyentuh snapshot resmi |
| Verifikasi 3 faktor | Staging: **9 dari 47** karyawan aktif bisa diverifikasi (19%) | Fallback **wajib diputuskan** sebelum implementasi |
| Analytics frontend | `index.html` memuat **PostHog + session recording** + `emergent-main.js` di semua halaman | Risiko kebocoran token/data di halaman publik → keputusan diperlukan |

---

## 1. Komponen Existing yang Dapat Direuse

### Backend
| Komponen | Lokasi | Reuse untuk |
|---|---|---|
| Data layer (dokumen gaya-Mongo di atas MariaDB, `TABLE_SPECS` + `INDEX_SPECS`, kolom `extra` JSON) | `app/core/db.py:204-720` | Definisi 3 tabel baru secara additive |
| Transaksi `transaction()` / `_TxWriter` | `app/core/db.py` | Submit atomik (submission + audit + status link) |
| Masking sensitif `mask_value`, `mask_employee`, `mask_for_audit` | `app/core/sensitive.py:12-64` | Prefill termasking, audit tanpa nilai penuh |
| Audit `build_audit_entry`, `log_action` (user_id boleh NULL, ip/user_agent) | `app/core/audit.py:33-129` | Seluruh jejak 01G |
| Validator field `digits_ok/date_ok/phone_ok/email_ok/enum_ok` | `app/core/field_validators.py` | Validasi draft/submit (konsisten dengan 01F) |
| Validator keluarga `FamilyInput` (relasi, NIK 16 digit, tanggal tidak di masa depan) | `app/routers/employee_profile.py:34-89` | Validasi usulan anggota keluarga |
| Enum master `RELIGIONS`, `EDUCATIONS`, gender, marital | `app/routers/employees.py:57-80` | Katalog label untuk form publik |
| Katalog completeness + `evaluate()` pure | `app/core/completeness_mapping.py:100-312`, `app/core/completeness.py:103-158` | Daftar kekurangan + perkiraan progres draft |
| Snapshot 01F `employee_completeness` | tabel existing | Sumber resmi "data yang masih kurang" (master saja) |
| Storage `object_path`, `put_object`, `get_object`, `guess_mime` | `app/core/storage.py:89-158` | Lampiran submission (private, proxy) |
| Signature check gambar `read_image_upload` (JPG/PNG/WEBP, ≤10 MB) | `app/core/branding_assets.py:42` | Foto profil usulan; pola untuk PDF |
| Validasi dokumen (`allowed_extensions`, `max_size_mb`, `MAX_UPLOAD_MB=15`) | `app/routers/documents.py:127-150` | Aturan upload per jenis dokumen |
| `READ_ONLY` middleware (blok non-GET) | `server.py:145-161` | Otomatis melindungi endpoint publik saat mode baca |
| Pola migration + ledger `schema_migrations` | `migrations/m0001…m0007` | `m0008_public_employee_form` |
| RBAC permission catalog + grant | `app/core/rbac.py` | Permission baru pengelolaan link |

### Frontend
| Komponen | Lokasi | Reuse untuk |
|---|---|---|
| `sectionFields(section, catalog)` (definisi field personal/bank_tax/bpjs) | `components/employees/ProfileSections.jsx:317-371` | Dasar field config form publik (disaring ke field editable) |
| Field keluarga inline | `ProfileSections.jsx:562-573` | Form anggota keluarga |
| Helper label `lbl()`, `enumOpt()`, `opt()` | `ProfileSections.jsx:318-319, 456-459` | Tampilkan label master, bukan ID |
| `CompletenessCard` (Wajib vs Anjuran, missing list) | `components/employees/CompletenessCard.jsx` | Pola visual "data yang perlu dilengkapi" |
| Shadcn (Sheet, Drawer, Progress, Tabs, Input, Select, Button, Sonner) + `DetailDrawer` | `components/ui/*`, `components/common/DetailDrawer.jsx` | Stepper mobile-first |
| Profile 360 page | `pages/EmployeeDetailPage.jsx` | Tempat tombol HR "Link Formulir Karyawan" |

### Yang perlu ditambah
- Router publik + dependency sesi publik (tanpa `get_auth`/RBAC internal).
- Token opaque (hash-only), sesi publik bertanda tangan, counter percobaan per-link.
- 3 tabel baru (link, submission+draft, file lampiran) — lihat §5.
- Klien API publik terpisah di frontend (instance axios **tanpa** interceptor bearer `hris_access_token`, `lib/api.js:11-17`), route publik di luar `ProtectedRoute` (`App.js:74-82, 113-114`).
- Endpoint katalog publik (katalog existing `GET /employees/catalog` butuh `employee:view`).

---

## 2. Klasifikasi Field

Sumber field: `TABLE_SPECS["employees"]` (`app/core/db.py:277-296`), keluarga (`:406-410`), dokumen (`:271-276`), gaji/PTKP di `employee_salaries` (payroll).

### A. Employee editable (diajukan, **tidak** langsung menimpa master)
| Section | Field |
|---|---|
| Data Pribadi | `full_name`* , `gender`, `birth_place`, `birth_date`*, `marital_status`, `religion`, `education`, foto profil (`photo_path` via lampiran) |
| Identitas | `nik`* (lihat catatan) |
| Kontak & Alamat | `phone`, `email` (pribadi), `address` (alamat KTP), `city`, `province`, `postal_code`, `domicile_address`, `emergency_contact_name`, `emergency_contact_phone` |
| Keluarga | usulan tambah / ubah / hapus `employee_family_members` (relationship, full_name, nik, birth_place, birth_date, gender, occupation, is_emergency_contact, phone) |
| Bank & Pajak | `bank_name`, `bank_account_number`, `bank_account_name`, `npwp`, pernyataan "tidak memiliki NPWP" (flag usulan, bukan `has_npwp` payroll) |
| BPJS | `bpjs_kesehatan_number`, `bpjs_tk_number` |
| Dokumen | unggah file untuk `document_types` dengan `owner_scope='employee'` (mis. KTP, KK, Ijazah, NPWP, Buku Tabungan) sebagai **lampiran submission** |
| Catatan | catatan bebas untuk HR |

\* **Field identitas/verifikasi** (`full_name`, `nik`, `birth_date`): usulan perubahan pada nilai yang **sudah ada** diusulkan **wajib disertai lampiran** (KTP) dan ditandai "perubahan identitas" untuk perhatian khusus di 01H. **Keputusan diperlukan (D4).**

### B. Employee view-only (label, tanpa ID teknis)
Nama perusahaan, `employee_number`, `join_date`, jabatan (`position_id` → label / `job_title`), departemen, lokasi kerja / project dari penempatan aktif 01D, status kepegawaian (label). Daftar dokumen yang **sudah ada** hanya berupa jenis + status ("KTP — sudah ada"), **tanpa unduh file master** (usulan).

### C. HR-only (tidak ditampilkan)
`status` legacy, `current_employee_status_id` (01B), `employment_status_id` sebagai data editable, `job_grade_id`, `cost_center_id`, `branch_id`, `division_id`, detail assignment 01D, kontrak (`employee_contracts`, termasuk `basic_salary`/`allowance`), sertifikasi (01G: tidak ada; dapat dibahas terpisah), seluruh `employee_salaries`/payroll (termasuk `ptkp_status`, `has_npwp`, enrolment BPJS), `notes` internal, `user_id`, `candidate_id`, `is_demo_data`, konfigurasi completeness, seluruh ID teknis/master.

**PTKP:** tidak diedit karyawan. Karyawan mengisi status pernikahan + keluarga; penetapan PTKP tetap HR/payroll (01H/payroll). Batasan PTKP TK/0 dari 01F tetap berlaku.

---

## 3. Kemampuan Verifikasi (Employee Number + NIK + Tanggal Lahir)

Query read-only di staging (valid = nomor karyawan ada, NIK 16 digit, tanggal lahir ISO valid 1930–hari ini, tidak duplikat dalam tenant):

| Tenant : status | Total | Bisa verifikasi | Tidak bisa | Penyebab utama |
|---|---:|---:|---:|---|
| KBS : active | 3 | **3** | 0 | — |
| NEP : active | 42 | **6** | 36 | tanpa tanggal lahir 35, tanpa NIK 20, NIK duplikat 1 (dengan karyawan berstatus deleted) |
| NEP : inactive | 5 | 5 | 0 | — |
| NEP : archived / deleted | 1 / 1 | 0 | 2 | tidak relevan (tidak boleh mendapat link) |
| SA077F / SB077F : active | 1 / 1 | 0 | 2 | tanpa NIK & tanggal lahir |
| **Total karyawan aktif** | **47** | **9 (19%)** | **38 (81%)** | |

Catatan:
- Sebagian besar karyawan NEP aktif adalah fixture uji (ZT01E 26, ZT01D 4, SMOKE 2) yang memang minim data. Baseline NEP aktif non-fixture: **5 dari 9** dapat diverifikasi.
- Angka produksi tidak dapat diketahui dari staging. Karena 01E Migration mengimpor data lama yang sering belum lengkap, **fallback wajib didesain**.
- Nomor karyawan: tidak ada unique index di DB (`ix_employee_number` non-unique, `db.py:654`), tetapi duplikat saat ini = 0. Desain di bawah **mengikat token ke satu employee**, sehingga verifikasi hanya membandingkan dengan data employee tersebut (tidak ada pencarian global → duplikat NIK/nomor tidak menyebabkan salah orang, dan tidak ada enumerasi).

### Proposal fallback (BELUM diimplementasikan — keputusan D1)
| Opsi | Cara kerja | Keamanan | Operasional |
|---|---|---|---|
| **F1 — Kode akses dari HR** (disarankan sebagai fallback) | Saat membuat link untuk karyawan yang NIK/tgl lahirnya kosong, HR memilih "gunakan kode akses". Sistem membuat kode 8 karakter (tampil sekali), disimpan hash. Verifikasi = nomor karyawan + kode akses (+ tanggal lahir/NIK bila tersedia). Kode dikirim HR lewat kanal berbeda dari link. | Baik (dua kanal), batas percobaan sama | Sedang |
| F2 — Verifikasi parsial | Nomor karyawan + faktor yang tersedia saja | Lemah (nomor karyawan mudah diketahui rekan kerja) | Mudah — **tidak disarankan** |
| F3 — Blok pembuatan link | Link hanya bisa dibuat jika NIK + tanggal lahir valid; HR melengkapi dulu di Profile 360 | Paling aman | Berat untuk data migrasi |

**Rekomendasi:** default F3 (link 3-faktor hanya bila data verifikasi lengkap), dengan F1 sebagai pilihan eksplisit HR per link (tercatat di audit). F2 tidak diimplementasikan.

---

## 4. Proposal Public Token & Session

### Link (invitation)
- Token: `secrets.token_urlsafe(32)` (256-bit). **Hanya hash SHA-256 yang disimpan** + `token_hint` (4 karakter terakhir) untuk tampilan HR.
- Tampil **sekali** saat dibuat (HR menyalin). Jika hilang → "Buat ulang link" (link lama otomatis REVOKED). Keputusan D2 (alternatif: simpan terenkripsi agar bisa disalin ulang — butuh kunci baru).
- **Satu link aktif per karyawan**; membuat link baru me-revoke link ACTIVE sebelumnya.
- Status: `ACTIVE` · `EXPIRED` (dihitung dari `expires_at`, juga ditulis saat diakses) · `REVOKED` · `SUBMITTED` · (`LOCKED` sementara saat percobaan gagal berlebih — atau diwakili `locked_until`).
- Masa berlaku default **7 hari** (HR dapat memilih 1–30 hari). Keputusan D3.
- Kolom jejak: `created_at/created_by`, `revoked_at/revoked_by/revoke_reason`, `last_opened_at`, `verified_at`, `submitted_at`.
- Link hanya berlaku bila: tenant aktif (status langganan tidak suspended/expired), modul inti aktif, karyawan tidak `deleted/archived` (usulan: hanya kategori status 01B ACTIVE/STANDBY — keputusan D5).

### Format URL (mencegah kebocoran token ke log)
- `uvicorn` access log mencatat path lengkap (terlihat di `backend.out.log`) → **token tidak boleh ada di path/query**.
- Usulan: `https://<frontend>/isi-data#<token>` — fragment (`#`) tidak pernah dikirim ke server/ingress/log. Frontend membaca fragment, lalu memanggil `POST /api/public/employee-form/open` dengan token di **body**, lalu `history.replaceState` untuk menghapus fragment dari address bar.
- Halaman publik: `<meta name="referrer" content="no-referrer">`, `Cache-Control: no-store` pada respons API publik.
- **Risiko analytics:** `public/index.html` memuat PostHog (dengan session recording) dan `emergent-main.js` di semua halaman. PostHog mencatat `$current_url` (termasuk fragment) dan merekam sesi. **Keputusan D6:** usulan — skrip PostHog tidak diinisialisasi pada route `/isi-data` (cek `location.pathname` sebelum `posthog.init`), atau halaman publik disajikan tanpa skrip analytics. Tanpa ini token dan tampilan data bisa terkirim ke pihak ketiga.

### Sesi publik (setelah verifikasi berhasil)
- Token sesi bertanda tangan (JWT HS256) dengan **audience `public-employee-form`**, `typ=public_form`, klaim `cid` (company), `eid` (employee), `lid` (link), `jti`; **kunci turunan terpisah** dari JWT login (mis. HMAC dari `JWT_SECRET` + label, atau env baru `PUBLIC_FORM_SECRET`). Tidak bisa dipakai di endpoint internal, dan token login tidak bisa dipakai di endpoint publik.
- Masa berlaku: **30 menit idle / 2 jam absolut** (sliding refresh saat Simpan Draft). Keputusan D3.
- Setiap request memeriksa ulang: link masih ACTIVE & belum expired, `eid/cid` sama dengan link → revoke link **langsung mematikan** semua sesi. Tidak perlu tabel sesi.
- Disimpan di `sessionStorage` (per tab), dikirim via header `Authorization` → **CSRF tidak relevan** (tanpa cookie).
- Replay: token link tetap bisa dipakai membuka ulang selama ACTIVE (untuk melanjutkan draft), tetapi selalu perlu verifikasi identitas ulang; setelah SUBMITTED hanya menampilkan status.

### Verifikasi
- Input: nomor karyawan, NIK, tanggal lahir → dinormalisasi (trim, hapus spasi/titik; tanggal ISO) → dibandingkan dengan `hmac.compare_digest` terhadap data employee **milik link tersebut saja**.
- Gagal → pesan generik tunggal: **"Data verifikasi belum sesuai. Silakan periksa kembali data yang Anda masukkan."** Tidak menyebut field yang salah, tidak mengonfirmasi keberadaan karyawan.
- Token tidak dikenal / expired / revoked → pesan generik "Link tidak valid atau sudah tidak berlaku. Hubungi HR." (token 256-bit tidak dapat ditebak; respons tidak memuat nama/perusahaan sebelum verifikasi — hanya logo/nama tenant, keputusan D7).
- Respons tidak pernah mengembalikan NIK/tanggal lahir.

---

## 5. Proposal Schema (m0008 — additive, tenant-aware)

Hanya **3 tabel** (sesi stateless, draft & submission satu tabel):

### 5.1 `employee_public_links`
| Kolom | Tipe | Keterangan |
|---|---|---|
| id, company_id, status, created_at/by, updated_at/by | COMMON | status: ACTIVE/EXPIRED/REVOKED/SUBMITTED |
| employee_id | fk | |
| token_hash | s64 | SHA-256 hex, **unique** |
| token_hint | s32 | 4 karakter terakhir |
| verification_mode | s32 | `IDENTITY_3F` atau `ACCESS_CODE` (bila F1 disetujui) |
| access_code_hash | s64 | nullable (F1) |
| expires_at | dt | |
| failed_attempts, total_failed_attempts | i | reset `failed_attempts` saat sukses/lock berakhir |
| locked_until, last_failed_at | dt | |
| last_opened_at, verified_at, submitted_at | dt | |
| revoked_at, revoked_by, revoke_reason | dt/fk/s512 | |
| submission_id | fk | submission terakhir dari link ini |

Index: `ux_public_link_token (token_hash)` unique · `ix_public_link_employee (company_id, employee_id, status)` · `ix_public_link_expiry (company_id, status, expires_at)`.

### 5.2 `employee_update_submissions` (draft + submission)
| Kolom | Tipe | Keterangan |
|---|---|---|
| id, company_id, status, created_at/by, updated_at | COMMON | status 01G: `DRAFT` → `PENDING_HR_VERIFICATION`; `CANCELLED`. Status 01H nanti: `APPROVED`, `PARTIALLY_APPROVED`, `REJECTED`, `CORRECTION_REQUESTED` |
| employee_id, link_id | fk | |
| source | s32 | `PUBLIC_EMPLOYEE_FORM` |
| open_slot | s64 | = employee_id selama DRAFT/PENDING/CORRECTION_REQUESTED, NULL setelah selesai → **unique (company_id, open_slot)** menjamin **1 submission terbuka per karyawan** (NULL boleh banyak) |
| proposed | j | `{fields:{…}, family:[{op:add/update/remove, family_id?, data}], no_npwp?, notes?}` — hanya field yang diubah |
| baseline | j | nilai master saat submit untuk field yang diubah (01H mendeteksi konflik jika master berubah setelah submit) |
| changed_fields | j | daftar nama field (tanpa nilai) untuk inbox/audit |
| identity_change | b | true jika full_name/nik/birth_date diusulkan berubah |
| draft_saved_at, submitted_at | dt | |
| version | i | optimistic lock untuk Simpan Draft (mencegah overwrite antar-tab) |
| submit_ip | s64 | |
| completeness_before | j | ringkasan 01F saat submit (skor, missing codes) — tanpa nilai |

Index: `ux_submission_open_slot (company_id, open_slot)` unique · `ix_submission_employee (company_id, employee_id, created_at)` · `ix_submission_status (company_id, status, submitted_at)` (untuk inbox 01H).

**Data sensitif di `proposed`/`baseline`:** master saat ini menyimpan NIK/NPWP/rekening/BPJS sebagai kolom biasa (tanpa enkripsi at-rest) dan melindunginya lewat masking API + audit. **Keputusan D8:** (A) konsisten dengan master — disimpan apa adanya, **selalu dimasking** di API/log/audit (disarankan untuk 01G); atau (B) enkripsi per-field (butuh kunci env baru + rotasi). Apa pun pilihannya: nilai sensitif **tidak pernah** masuk audit/log/error.

### 5.3 `employee_submission_files`
| Kolom | Tipe | Keterangan |
|---|---|---|
| id, company_id, status, created_at | COMMON | status: `active` / `removed` (dihapus dari draft) |
| submission_id, employee_id | fk | |
| document_type_id | fk | jenis dokumen `owner_scope='employee'`; atau `purpose='PHOTO'` |
| purpose | s32 | `DOCUMENT` / `PHOTO` / `IDENTITY_PROOF` |
| file_name (tersanitasi), file_extension, mime_type, file_size, sha256 | s/s64/s/bi/s64 | |
| storage_path | s512 | `{R2_PREFIX}/companies/{cid}/employee-submissions/{submission_id}/{file_id}.{ext}` |
| document_number, issued_date, expiry_date | s/s32/s32 | metadata opsional untuk 01H |

Index: `ix_submission_file (company_id, submission_id)`.

**Mengapa tidak reuse tabel `documents`:** baris `documents` dengan owner karyawan langsung dihitung oleh 01F (`DOC.*`) dan muncul di daftar dokumen HR/Profile 360 → melanggar "draft/pending bukan master". Tabel terpisah menjaga isolasi; 01H saat approve cukup membuat baris `documents` yang menunjuk `storage_path` yang sama (tanpa salin file, file lama tidak dihapus).

### Permission (m0008)
- `employee_public_form:manage` — buat/revoke/lihat link (grant: `tenant_admin`, `hr_admin`; `company_owner` wildcard). Keputusan D9 (apakah `hr_manager` ikut).
- Permission inbox/approve **ditunda ke 01H**.

---

## 6. Proposal Upload Dokumen

- Hanya lewat sesi publik yang valid, ke submission milik sesi (DRAFT).
- Allow-list: irisan `document_types.allowed_extensions` dengan allow-list publik `pdf,jpg,jpeg,png,webp`; foto profil `jpg,png,webp`.
- Ukuran: `min(document_types.max_size_mb, batas publik 10 MB)`; maks **20 file per submission**, maks 3 file per jenis dokumen.
- **Validasi signature (magic bytes)**: PDF `%PDF-`, JPEG `FF D8 FF`, PNG `89 50 4E 47`, WEBP `RIFF…WEBP` — tidak hanya ekstensi/MIME dari browser. Reuse pola `read_image_upload`.
- Nama file disanitasi (tanpa path, panjang dibatasi); nama asli **tidak** dimasukkan ke audit (bisa memuat NIK), cukup jenis + ukuran.
- Private: disimpan di prefix submission, **tidak ada URL publik/presigned permanen**. Pratinjau file milik sendiri lewat proxy API bersesi (`Cache-Control: private, no-store`).
- File/dokumen existing **tidak** ditimpa/dihapus; penggantian dilakukan di 01H.
- Kamera HP: `<input type="file" accept="image/*,application/pdf" capture>` opsional; iOS mengonversi HEIC → JPEG saat `accept` memuat `image/jpeg`. HEIC native tidak didukung di 01G.
- File yang dihapus dari draft: status `removed` + objek dihapus dari storage (masih draft, belum pernah disubmit). Draft yang dibatalkan/expired: pembersihan dijadwalkan (job harian existing) — keputusan D10 (retensi mis. 30 hari).

---

## 7. Proposal Security & Rate Limit

| Ancaman | Kontrol |
|---|---|
| Tebak token | 256-bit random, hash-only di DB, lookup via unique index |
| Brute force verifikasi | Per-link: **5 gagal → lock 15 menit**; **total 10 gagal → link otomatis REVOKED** (HR buat ulang). Disimpan di baris link (tahan restart, multi-instance) |
| Flood per IP | Limiter in-memory per IP (mis. 20 open/verify per menit, 60 request form per menit). **Catatan:** `ctx.ip` memakai hop pertama `X-Forwarded-For` (`deps.py:79-85`), yang bisa dipalsukan klien → limiter IP hanya lapisan tambahan; kontrol utama tetap counter per-link |
| Enumerasi karyawan | Token terikat ke employee; tidak ada endpoint pencarian; pesan gagal generik; tanpa data sebelum verifikasi |
| Timing | `hmac.compare_digest`, alur respons seragam |
| Tenant isolation | Semua query `company_id` dari baris link; sesi membawa `cid/eid/lid` dan dicek ulang terhadap link |
| Lintas karyawan | Endpoint tidak menerima `employee_id` dari klien; selalu dari sesi |
| Pemakaian ulang sesi | Sesi pendek + cek status link tiap request; revoke = putus |
| Kebocoran token | Fragment URL, token di body, no-referrer, no-store, token tidak di log/audit (hanya `token_hint`/link id), analytics dikecualikan (D6) |
| CSRF | Tidak relevan (Bearer header, tanpa cookie); CORS existing tetap |
| Upload berbahaya | Allow-list + magic bytes + batas ukuran/jumlah + prefix private + proxy download |
| Respons sensitif | Prefill termasking (`mask_value`), tidak ada ID teknis/master, label saja |
| Mode baca | Middleware `READ_ONLY` existing otomatis memblok POST/PUT publik |
| Status tenant | Link ditolak jika tenant suspended/expired atau modul inti nonaktif |
| Log aplikasi | Logger hanya mencatat link id / hint; tidak mencatat body permintaan publik |

---

## 8. Audit Trail

Via `build_audit_entry`/`log_action`, `module="employee_public_form"`, `user_id=NULL` untuk aksi publik (aksi HR memakai user HR), ip + user_agent dari request.

| Action | record | Isi (tanpa nilai sensitif / token) |
|---|---|---|
| `public_link.create` | link id | employee, expires_at, verification_mode, token_hint |
| `public_link.revoke` | link id | alasan, oleh siapa (HR) / `AUTO_BRUTE_FORCE` |
| `public_link.expire` | link id | (saat terdeteksi) |
| `public_form.verify_success` | link id | — |
| `public_form.verify_failed` | link id | nomor percobaan, locked? (tanpa input apa pun) |
| `public_form.draft_saved` | submission id | `changed_fields` (nama field saja) |
| `public_form.submitted` | submission id | changed_fields, identity_change, jumlah file |
| `public_form.file_uploaded` / `file_removed` | submission id | jenis dokumen, ukuran |
| `submission.reopened` | submission id | (01H — disiapkan) |

Audit untuk `verify_failed` dibatasi agar serangan tidak membanjiri `audit_logs` (mis. dicatat per percobaan hanya sampai lock; berikutnya teragregasi).

---

## 9. Integration Point 01C + 01F

### 01C (Profile 360)
- **Baca saja** di 01G: prefill dari `employees`, `employee_family_members`, keberadaan `documents` (owner karyawan), label master & penempatan 01D.
- **Tidak ada tulis** ke master di 01G (tidak memanggil `PUT /employees/{id}`, family CRUD, upload dokumen/foto master).
- HR UI: kartu/dialog **"Link Formulir Karyawan"** di Profile 360 (buat, salin, revoke, status link, status submission terakhir: Draft / Menunggu Verifikasi HR).

### 01F (Data Completeness)
- Daftar "Data yang masih perlu dilengkapi" = snapshot resmi `employee_completeness` (master saja), disaring ke kategori yang bisa diisi karyawan: `PERSONAL.*` (kecuali yang HR-only), `BANK.ACCOUNT`, `TAX.NPWP`, `BPJS.*`, `FAMILY.SPOUSE`, `DOC.*` (jenis dokumen karyawan). Kategori `EMPLOYMENT.*`, `PLACEMENT.*`, `CONTRACT.*`, `CERT.*`, `TAX.PTKP` → tidak ditampilkan atau hanya ditandai "dilengkapi oleh HR".
- **Wajib vs Anjuran** dibedakan (level dari rules tenant).
- Persentase resmi tetap dari snapshot master. Progres draft ditampilkan terpisah sebagai **"perkiraan setelah diverifikasi HR"** dengan `evaluate()` pure atas master⊕draft — **tidak** ditulis ke snapshot, tidak memicu refresh 01F.
- Submission tidak memicu `safe_refresh` (master tidak berubah). Refresh 01F terjadi di 01H setelah approval.

---

## 10. Batas 01G vs 01H

| 01G (scope ini) | 01H (berikutnya) |
|---|---|
| HR buat / salin / revoke link per karyawan | Inbox submission HR |
| Verifikasi identitas + sesi publik | Bandingkan Lama vs Baru (termasuk deteksi konflik baseline) |
| Form mobile-first, prefill termasking | Approve / approve sebagian / reject / minta koreksi (reopen) |
| Simpan Draft, Kirim untuk Verifikasi | Terapkan perubahan ke Profile 360 (employees, keluarga) |
| Lampiran dokumen ke submission (private) | Jadikan lampiran sebagai `documents` resmi / ganti dokumen lama |
| Status "Menunggu verifikasi HR" | Recalculate completeness 01F setelah approve |
| Audit event 01G | Notifikasi hasil ke karyawan (email/WA dibahas terpisah) |

01G **tidak** membangun inbox/approval dan **tidak** mengubah master.

---

## 11. Risiko & Regression Impact

| Risiko | Dampak | Mitigasi |
|---|---|---|
| Endpoint publik pertama yang menerima tulis tanpa login | Tinggi (keamanan) | Router terpisah, dependency sesi publik, tes keamanan khusus (enumerasi, brute force, lintas tenant/karyawan, kebocoran token di log) |
| PostHog/session recording di halaman publik | Tinggi (privasi) | Keputusan D6 sebelum UI publik dibuat |
| Token di access log | Tinggi | Fragment + body (bukan path) |
| Sebagian besar data migrasi tanpa NIK/tgl lahir | Tinggi (operasional) | Keputusan D1 (F3 + F1) |
| `X-Forwarded-For` dapat dipalsukan | Sedang | Counter per-link sebagai kontrol utama |
| Konflik: master berubah (HR/impor 01E) saat submission pending | Sedang | `baseline` disimpan; ditangani 01H |
| Interceptor axios global menambah token HR bila HR membuka link di browser yang sama | Rendah | Instance axios publik terpisah |
| Regresi 01B–01F | Rendah | Perubahan additive: tabel baru, router baru, satu kartu baru di Profile 360; tidak mengubah alur existing. Regresi 01B/01C/01D/01E/01F/tenant dijalankan ulang |
| READ_ONLY mode | — | Otomatis terblok (sesuai perilaku staging/produksi) |
| Infrastruktur MariaDB staging (change buffer) | — | Isu terpisah (pre-production), bukan scope 01G |

---

## 12. Migration yang Diperkirakan

- **`m0008_public_employee_form`** (setelah m0007):
  - `CREATE TABLE` `employee_public_links`, `employee_update_submissions`, `employee_submission_files` + index di atas.
  - Permission `employee_public_form:manage` + grant (`tenant_admin`, `hr_admin`).
  - Tanpa DROP/ALTER tabel existing, tanpa backfill; dry-run default, `--apply` eksplisit, ledger `schema_migrations`, rerun = SKIP.
- Tambahan `TABLE_SPECS`/`INDEX_SPECS` di `app/core/db.py` (additive).
- Env baru (opsional, keputusan): `PUBLIC_FORM_SECRET` (atau turunan dari `JWT_SECRET`). Tidak perlu `PUBLIC_BASE_URL` untuk 01G karena link disusun di frontend (`window.location.origin`); baru dibutuhkan bila email dipakai.

---

## 13. Urutan Implementasi 01G (setelah review)

1. **G0** — Branch `feature/upgrade-01g-public-employee-form` dari HEAD saat ini (lokal, tanpa push); keputusan D1–D10 dicatat di plan.
2. **G1** — `m0008` + `TABLE_SPECS` + permission; dry-run → apply → rerun SKIP.
3. **G2** — Backend HR: buat/list/revoke link (show-once token), audit.
4. **G3** — Backend publik: `open` (status link saja), `verify` (3 faktor / kode akses, counter + lock), penerbitan sesi, `GET form` (prefill termasking + label + daftar kekurangan 01F + katalog publik).
5. **G4** — Draft (PUT dengan `version`) + Submit (transaksi: submission PENDING + link SUBMITTED + audit; aturan 1 submission terbuka) + halaman status.
6. **G5** — Upload lampiran (allow-list, magic bytes, batas) + pratinjau file sendiri via proxy.
7. **G6** — Tes backend: fungsional + keamanan (brute force, enumerasi, lintas tenant/karyawan, sesi kedaluwarsa/revoke, token tidak ada di log/audit, sensitif tidak bocor) + regresi 01B–01F.
8. **G7** — `design_agent` untuk panduan UI publik mobile-first → UI HR (kartu link di Profile 360) + UI publik (stepper: Verifikasi → Data Pribadi → Kontak & Alamat → Keluarga → Bank & Pajak → BPJS → Dokumen → Tinjau & Kirim; progres, Simpan Draft jelas, error per field, tanpa tabel lebar).
9. **G8** — esbuild + `yarn build`, screenshot mobile/tablet/desktop, `testing_agent_v3`, perbaikan.
10. **G9** — Laporan 01G, STOP untuk review.

---

## 14. Keputusan yang Dibutuhkan Sebelum Coding

| # | Keputusan | Usulan |
|---|---|---|
| D1 | Fallback karyawan tanpa NIK/tgl lahir | F3 default + F1 (kode akses HR) opsional; F2 tidak |
| D2 | Token link tampil sekali vs dapat disalin ulang | Tampil sekali + "Buat ulang link" |
| D3 | Masa berlaku link & sesi | Link 7 hari (1–30); sesi 30 menit idle / 2 jam absolut |
| D4 | Perubahan field identitas (nama, NIK, tgl lahir) | Boleh diusulkan, wajib lampiran KTP, ditandai `identity_change` |
| D5 | Status karyawan yang boleh diberi link | Kategori 01B ACTIVE & STANDBY; tolak INACTIVE/archived/deleted |
| D6 | Analytics (PostHog + session recording) di halaman publik | Tidak diinisialisasi pada route `/isi-data` |
| D7 | Tampilan sebelum verifikasi | Hanya logo/nama tenant + form verifikasi; tanpa nama karyawan |
| D8 | Penyimpanan nilai sensitif di submission | (A) konsisten dengan master + masking ketat |
| D9 | Siapa yang boleh membuat/revoke link | `tenant_admin`, `hr_admin` (+ `hr_manager`?) |
| D10 | Retensi draft batal/expired + file-nya | Bersihkan otomatis setelah 30 hari via job harian existing |
| D11 | Setelah Submit | Link → SUBMITTED; buka ulang hanya menampilkan status; edit menunggu 01H (minta koreksi/reopen) atau HR buat link baru setelah submission selesai diproses |

---

**Status: 01G AUDIT & DESIGN SELESAI — STOP menunggu review.** Tidak ada kode 01G, migration, atau perubahan data yang dibuat. Production Changed: NO.
