# UPGRADE 01H — HR VERIFICATION · AUDIT (STEP 1, AUDIT ONLY)

Status: **AUDIT SELESAI — MENUNGGU REVIEW USER SEBELUM CODING**
Konteks: 01F LOCKED ✅ · 01G Public Form LOCKED ✅ · 01G Form Builder LOCKED ✅ (PR #16 open, belum merge) · **01H: AUDIT ONLY** · 01I/01J: NOT STARTED
Production Changed: **NO** · Tidak ada perubahan kode produk, tabel, data, push, PR, merge, atau deploy pada langkah ini.

Provenance: semua temuan di bawah berasal dari pembacaan kode (read-only) oleh agent + 1 query hitung read-only pada
database staging. Belum ada pengujian fungsional 01H (belum ada kode 01H).

Legenda klasifikasi: **REUSE** = pakai apa adanya · **MODIFY** = ubah kode/struktur existing (aditif) ·
**NEW** = dibuat baru (hanya bila existing terbukti tidak cukup) · **DEFER** = di luar 01H / ditunda.

---

## 1. Ringkasan eksekutif

1. Fondasi 01H **sudah sebagian besar tersedia**: submission (`employee_update_submissions`) sudah menyimpan
   `proposed` + `baseline` (snapshot nilai lama saat submit) + `version` (optimistic lock) + slot unik satu pengajuan
   terbuka per karyawan. Tabel nilai custom resmi (`employee_custom_field_values`) sudah dibuat di m0009 dan memang
   dirancang "hanya ditulis oleh approval 01H". Audit log dengan masking, trigger 01F `safe_refresh`, helper transaksi
   DB, dan jalur tulis master (repo/update) semuanya siap dipakai ulang.
2. **Tidak perlu tabel baru dan tidak perlu approval engine baru.** Engine `approval_workflows` existing hanya metadata
   multi-step untuk modul lain (leave/payroll/dll) — terlalu berat untuk keputusan satu-langkah HR dan tidak punya
   eksekusi generik. Rekomendasi: status + beberapa kolom review **aditif (NULL)** pada tabel submission existing.
3. Gap utama: (a) status keputusan (APPROVED/REJECTED/REVISION_REQUESTED) belum ada; (b) kolom reviewer/catatan belum
   ada; (c) belum ada endpoint HR untuk melihat detail usulan & memutuskan; (d) belum ada logika "apply" (core, keluarga,
   dokumen/foto, custom); (e) belum ada deteksi konflik; (f) belum ada permission khusus verifikasi; (g) belum ada UI
   perbandingan (diff) — harus dibuat baru.
4. Rekomendasi inti: **keputusan per pengajuan (satu klik Setujui/Tolak/Minta Perbaikan)**, dengan **resolusi eksplisit
   hanya untuk item yang konflik**; apply **all-or-nothing dalam satu transaksi**; revisi memakai **baris submission
   yang sama** (tanpa duplikat).

---

## 2. Komponen existing (bukti + klasifikasi)

### 2.1 Submission & draft (01G)
| Komponen | Bukti (path:line) | Temuan | Klasifikasi |
|---|---|---|---|
| Tabel `employee_update_submissions` | `backend/app/core/db.py:472-476` (+ COMMON `status`, audit fields `db.py:207-214`) | Kolom: `employee_id, link_id, source, open_slot, proposed(J), baseline(J), changed_fields(J), identity_change, version, draft_saved_at, submitted_at, submit_ip, completeness_before(J)` | **REUSE** + **MODIFY** (kolom review aditif, §6) |
| Status submission | `backend/app/core/public_form.py:33-34` | Hanya `DRAFT`, `PENDING_HR_VERIFICATION`. `OPEN_SUBMISSION_STATUSES=(DRAFT,PENDING)`. Tidak ada APPROVED/REJECTED/REVISION di seluruh kode. | **MODIFY** (tambah 3 status) |
| Satu pengajuan terbuka per karyawan | `db.py:774` `ux_submission_open_slot (company_id, open_slot)`; `open_slot = employee_id` saat terbuka (`public_employee_form.py:865`) | Belum ada kode yang melepas `open_slot` (belum ada status akhir). | **REUSE** (+ set `open_slot=NULL` saat APPROVED/REJECTED) |
| Nilai usulan (proposed) | `public_employee_form.py:838-839` | `{"fields":{core diffs}, "family":[{op add/update/remove, ref, data/reason}], "notes", "no_npwp", "custom":{cf_* diffs}, "meta":{form_version}}` — hanya berisi perubahan (diff), sudah tervalidasi whitelist. | **REUSE** |
| Nilai lama/baseline | `public_employee_form.py:973-979, 992` | Di-snapshot **saat submit**: `baseline.fields` (nilai master saat itu), `baseline.custom` (nilai custom resmi), `baseline.family` (baris keluarga yang direferensikan). Tidak ada hash/`updated_at` employee. | **REUSE** — cukup untuk deteksi konflik per field (§10) |
| Optimistic lock submission | `version` + `select_one_for_update` (`public_employee_form.py:916-924, 987-990`) | Pola sudah terbukti. | **REUSE** untuk endpoint keputusan HR |
| Snapshot 01F sebelum | `completeness_before` (`public_employee_form.py:994-995`) | Skor & missing codes saat submit. | **REUSE** (+ `completeness_after` baru) |
| Editability publik | `_ensure_editable` `:858-860`; `get_form` read-only `:666`; `portal_verify` status `:461-462` | Terkunci bila PENDING. Portal: status sesi = SUBMITTED hanya bila PENDING. | **MODIFY** (REVISION_REQUESTED = dapat diedit) |
| Link undangan | `employee_public_links` (`db.py:463-469`), ditandai `SUBMITTED` saat submit `:997-998`; buat link baru diblok hanya bila PENDING `:224-227` | Jalur undangan = opsional; jalur utama = portal. | **REUSE** (revisi via portal; HR boleh buat undangan baru saat REVISION_REQUESTED — sudah diizinkan oleh kode existing) |

### 2.2 Lampiran pending
| Komponen | Bukti | Temuan | Klasifikasi |
|---|---|---|---|
| `employee_submission_files` | `db.py:477-482`; upload `public_employee_form.py:1021-1084` | Kolom: `submission_id, employee_id, document_type_id/code, purpose (DOCUMENT/PHOTO/CUSTOM_FIELD), file_name, ext, mime, size, sha256, storage_path, uploaded_at, field_key`. Status hanya `active`/`removed`. Object di prefix `.../employee-submissions/{submission_id}/...` (private). | **REUSE** + **MODIFY** (status `PROMOTED`/`REJECTED`, kolom `document_id`) |
| Promosi ke dokumen resmi | tidak ada (grep) — pesan eksplisit "Belum menjadi dokumen resmi" `:1084` | Belum ada. | **NEW** (logika apply, bukan tabel) |

### 2.3 Master karyawan, keluarga, dokumen, foto (01C)
| Komponen | Bukti | Temuan | Klasifikasi |
|---|---|---|---|
| Update master | `routers/employees.py:452-511` (`PUT /employees/{id}`) | Tolak nilai masking, blok `status`/`project_id`, unik `nik`, `repo.update`, audit before/after (masked), `completeness.safe_refresh`. Logika ada di route (belum jadi service). | **REUSE aturan** / **MODIFY ringan**: pindahkan aturan inti ke helper bersama agar approval memakai validasi yang sama (tanpa mengubah perilaku PUT) |
| Repo generik | `core/repo.py:99-111` `TenantRepository.update()` | Apply dict patch tenant-scoped, return (before, after). Tidak ada kolom versi pada `employees` (`db.py:291-310`). | **REUSE** (konflik ditangani via baseline, §10) |
| Validasi nilai field publik | `core/public_form.py:238-262` `EDITABLE_FIELDS`, `normalize_value`, `validate_field` | Whitelist 23 field core + validator. | **REUSE** (divalidasi ulang saat approve) |
| Keluarga | `db.py:420-424`; CRUD `routers/employee_profile.py:109-162` (`FamilyInput` 34-89; delete = `hard_delete` `:158`) | Tidak ada service terpisah; pola `TenantRepository`. | **REUSE** pola + `FamilyInput` |
| Dokumen | `db.py:285-290` (owner_type/owner_id, **tanpa** `employee_id`, `version`, `is_deleted`); upload `routers/documents.py:102-187`; path `object_path()` `core/storage.py:89-91` | Tidak ada kolom verifikasi/official; tidak ada supersede; storage tanpa fungsi copy (hanya put/get/delete). | **REUSE** tabel `documents` (tidak ada storage dokumen baru) |
| Foto profil | `routers/employee_profile.py:166-205` | Path wajib di prefix `.../employees/{id}/photo/` (dicek saat GET `:173`). Ganti foto = hapus objek lama. | **REUSE** pola (object disalin ke prefix foto) |
| Timeline Profile 360 | `employee_profile.py` `TIMELINE_RESOURCES=("employee","contract","certification","document")` | Timeline dibangun dari `audit_logs`. | **REUSE** — perubahan hasil approval otomatis muncul bila di-audit dengan resource `employee`/`document` |
| Status history | `employee_status_history` (`db.py:413-418`) | Khusus status bisnis; tidak relevan untuk pembaruan data pribadi. | **DEFER** (tidak dipakai 01H) |

### 2.4 Custom field (01G Form Builder)
| Komponen | Bukti | Temuan | Klasifikasi |
|---|---|---|---|
| `employee_custom_field_values` | `db.py:498-501`, unik `(company_id, employee_id, field_key)` `db.py:785` | Kolom `employee_id, field_key, value(J), value_text, source_submission_id`. Komentar: "Nilai custom RESMI ... Hanya ditulis oleh approval 01H." Staging: **0 baris**. Public router hanya membaca. | **REUSE** (01H = satu-satunya penulis) |
| Definisi & validasi custom | `core/form_builder.py:258+` `validate_custom`, `visible_custom` `:252`, reserved/protected `:53-84` | Validasi per tipe; tipe `file` via lampiran. | **REUSE** |

### 2.5 01F Completeness
| Komponen | Bukti | Temuan | Klasifikasi |
|---|---|---|---|
| Recompute per karyawan | `core/completeness.py:459` `safe_refresh(company_id, [ids], reason, user_id)` (tidak pernah raise) | Sudah dipanggil otomatis oleh update master/keluarga/foto/dokumen. | **REUSE** — cukup satu panggilan setelah apply commit |
| NPWP "tidak punya" | `completeness_mapping.py:128` TAX.NPWP `app="has_npwp"`; sumber `employee_salaries.has_npwp` (`completeness.py:192-193`, `db.py:346`) | Flag `no_npwp` dari form publik akan menyentuh **tabel payroll** bila di-apply. | **DEFER** apply otomatis (lihat §4.F) |

### 2.6 Audit
| Komponen | Bukti | Temuan | Klasifikasi |
|---|---|---|---|
| `audit_logs` + `log_action` / `build_audit_entry` | `db.py:335-339`; `core/audit.py:33-91` | Before/after disimpan setelah `_sanitize` + `mask_for_audit` (NIK, rekening, NPWP, BPJS dimasking rekursif — `core/sensitive.py:12-64`). `build_audit_entry` untuk insert di dalam transaksi. | **REUSE** |

### 2.7 Approval infrastructure existing
| Komponen | Bukti | Temuan | Klasifikasi |
|---|---|---|---|
| `approval_workflows` / `approval_steps` | `routers/approvals.py:13-24`, `db.py:321-330` (staging: 13 workflow) | Metadata multi-step untuk `recruitment, contract, leave, overtime, attendance, mobilization, expense, payroll, finance_request`. Eksekusi approve/reject ditulis per modul. Tidak mencakup data karyawan. | **DEFER** (tidak dipakai; terlalu berat untuk keputusan satu langkah; bisa diintegrasikan kelak bila PT REAL butuh multi-level) |

### 2.8 Tenant / RBAC / scope / sesi publik
| Komponen | Bukti | Temuan | Klasifikasi |
|---|---|---|---|
| Tenant isolation | `core/deps.py:230,267-284` (`ctx.company_id` dari JWT), `core/tenancy.py` `TenantCollection` (auto-inject/validasi `company_id`) | Terbukti dipakai di seluruh router 01G. | **REUSE** |
| Permission | `core/rbac.py:58-65`, `default_role_permissions()` `:142-239`; `require_permission()` `core/deps.py:322-340` | Tidak ada `employee:verify/approve`. Pola penambahan permission + grant = m0009. | **MODIFY** (tambah `employee_form:verify`, §9) |
| Masking tampilan HR | `core/sensitive.py:27` `can_view_sensitive(ctx)` (= punya `employee:edit`), `apply_employee_masking` | Aturan Profile 360 existing. | **REUSE** |
| Project/data scope HR | tidak ada helper scope baris (grep rbac/deps) | RBAC company-wide; project hanya filter query. | **REUSE filter project**, scope baris **DEFER** |
| Sesi publik terpisah | `public_employee_form.py:512-534` (`session_hash` di `employee_public_links`) vs JWT `deps.py` | Token sesi publik tidak dapat melewati `require_permission`. | **REUSE** (dibuktikan ulang di test, §12) |
| Monitoring Form Builder | `routers/employee_form_builder.py:55-102` (`_MON_SQL`: has_draft/has_submitted/has_pending) | Belum mengenal status baru. | **MODIFY** kecil (hitungan status baru) |

### 2.9 Frontend
| Komponen | Bukti | Klasifikasi |
|---|---|---|
| Navigasi grup Kepegawaian | `frontend/src/lib/nav.js:99-108` (items: employees, employee-completeness, employee-update-form, reminders) | **MODIFY** (tambah item "Verifikasi Pembaruan Data") |
| Route | `frontend/src/App.js:151-152` | **MODIFY** (route baru) |
| Profile 360 display | `frontend/src/pages/EmployeeDetailPage.jsx`, `frontend/src/components/employees/ProfileSections.jsx` | **REUSE** label/format |
| Komponen diff/compare | tidak ada | **NEW** |
| Form publik | `frontend/src/pages/public/PublicEmployeeFormPage.jsx` | **MODIFY** kecil (banner "Perlu perbaikan" + catatan HR; banner keputusan terakhir) |

### 2.10 Notifikasi
Email SMTP ada (`core/mailer.py`, `core/reminder_mail.py`); in-app notification tidak ada. → Notifikasi keputusan ke
karyawan **DEFER** (karyawan melihat status saat login portal; HR menginformasikan manual).

---

## 3. Gap (yang benar-benar belum ada)
| # | Gap | Klasifikasi |
|---|---|---|
| G1 | Status APPROVED / REJECTED / REVISION_REQUESTED + transisi | MODIFY |
| G2 | Kolom reviewer, catatan, riwayat keputusan, hasil apply, completeness_after | MODIFY (kolom aditif NULL) |
| G3 | Endpoint HR: daftar, ringkasan, detail (Data Saat Ini vs Usulan), unduh lampiran, approve/reject/request-revision | NEW (router) |
| G4 | Service apply: core, keluarga, dokumen, foto, custom — satu transaksi | NEW (modul `core/hr_verification.py`) |
| G5 | Deteksi konflik baseline vs master terkini | NEW (logika, tanpa tabel) |
| G6 | Permission verifikasi | MODIFY (rbac + migrasi grant) |
| G7 | UI Verifikasi Pembaruan Data + komponen diff | NEW |
| G8 | Jalur revisi di form publik (baris sama) | MODIFY |
| G9 | Status lampiran PROMOTED/REJECTED + tautan `document_id` | MODIFY |

---

## 4. Keputusan desain (rekomendasi)

### A. Granularitas approval
| Opsi | Kelebihan | Kekurangan |
|---|---|---|
| **Per pengajuan (satu keputusan)** | Paling mudah dipahami HR; satu hasil jelas; audit sederhana; tidak ada data "setengah jadi"; cocok dengan skala PT REAL (±100 karyawan, pengajuan sporadis) | Bila satu bagian salah, seluruh pengajuan perlu perbaikan |
| Per section | Fleksibel sedang | Status parsial membingungkan karyawan ("sebagian disetujui"); lampiran/field lintas section; state machine lebih rumit |
| Per field | Paling fleksibel | Paling rumit untuk HR & karyawan; risiko data tidak konsisten (mis. nomor rekening disetujui, nama pemilik rekening ditolak); banyak klik; audit rumit |

**Rekomendasi: per pengajuan.** Setujui = semua perubahan diterapkan; Tolak = tidak ada yang diterapkan; ada bagian yang
salah → **Minta Perbaikan** dengan catatan (opsional menandai item yang perlu diperbaiki).
Satu-satunya pilihan per item: **item yang konflik** (§4.C) wajib diputuskan eksplisit (Pakai usulan / Pertahankan data
saat ini). HR **tidak mengedit nilai usulan** di layar verifikasi (menjaga backend authoritative & jejak jelas; koreksi
kecil setelah approve tetap bisa lewat Profile 360 seperti biasa).

### B. Request Revision (tanpa duplikat)
- Baris submission **sama**: `PENDING_HR_VERIFICATION → REVISION_REQUESTED` (tetap "terbuka", `open_slot` tetap terisi →
  unik satu pengajuan per karyawan tetap terjaga). `revision_count += 1`, catatan HR disimpan (`review_note`), entri
  ringkas ditambahkan ke `review_history` (tanpa nilai data), audit `employee_update.revision_requested`.
- Karyawan login portal seperti biasa → form **dapat diedit** dengan draft sebelumnya + banner "Perlu perbaikan: <catatan HR>"
  (+ item yang ditandai). Lampiran tetap `active` (bisa dihapus/diganti oleh karyawan).
- Kirim ulang → `REVISION_REQUESTED → PENDING_HR_VERIFICATION` pada baris yang sama; **baseline & completeness_before
  diambil ulang** saat submit ulang; `version` naik.
- Jalur undangan: link lama tetap `SUBMITTED` (read-only); karyawan memakai portal (jalur utama) atau HR membuat undangan
  baru (kode existing sudah mengizinkan selain PENDING).
- Tidak ada batas jumlah revisi di 01H (DEFER; bisa ditambah bila perlu).

### C. Konflik (data resmi berubah setelah submit)
- Deteksi saat detail dibuka **dan** diulang di dalam transaksi approve: bandingkan `baseline` (nilai saat submit) dengan
  data resmi terkini (normalisasi sama dengan form).
- Per item: `OK` (tidak berubah) · `ALREADY_APPLIED` (data resmi sudah sama dengan usulan → no-op) · `CONFLICT` (berubah
  oleh pihak lain setelah submit).
- **Approve diblok (409)** selama ada `CONFLICT` yang belum diresolusi. HR memilih per item konflik: **Pakai usulan
  karyawan** atau **Pertahankan data saat ini** — keputusan tercatat di `apply_result` + audit. Tidak pernah silently
  overwrite. Alternatif bagi HR: Minta Perbaikan.
- Keluarga: `update/remove` konflik bila baris berubah atau sudah dihapus (baris hilang → item tidak dapat diterapkan,
  harus "Pertahankan data saat ini"). `add` → peringatan bila sudah ada anggota dengan NIK sama / nama+hubungan sama.
- Custom: konflik bila nilai resmi berubah sejak baseline; definisi custom nonaktif/terhapus → item ditandai
  "tidak akan diterapkan" (tidak blok).
- Karyawan tidak lagi aktif / terhapus → approve diblok; hanya Tolak.
- Race dua HR: `version` + `SELECT ... FOR UPDATE` → keputusan kedua mendapat 409 "sudah diproses".

### D. Dokumen & file — lifecycle
```
upload publik  → employee_submission_files.status = active (private, prefix employee-submissions/...)
  ├─ karyawan hapus (draft/revisi)  → removed            (existing)
  ├─ HR Minta Perbaikan             → tetap active (karyawan dapat hapus/ganti)
  ├─ HR Tolak                       → REJECTED (object tetap private; tidak pernah jadi resmi; purge = kebijakan retensi DEFER)
  └─ HR Setujui:
       DOCUMENT     → baris baru di `documents` (owner_type=employee, owner_id, document_type_id, version=1),
                      object DISALIN ke path resmi `object_path()` (sama dengan upload manual) → file.status=PROMOTED, document_id diisi
       PHOTO        → object DISALIN ke prefix foto → employees.photo_path/photo_version (perilaku = upload foto existing,
                      termasuk penghapusan objek foto lama) → file.status=PROMOTED
       CUSTOM_FIELD → TIDAK menjadi dokumen resmi; nilai resmi custom = referensi {submission_file_id, file_name, mime, size}
                      di employee_custom_field_values → file.status=PROMOTED (tidak pernah di-purge)
```
- Dokumen existing dengan tipe sama **tidak dihapus/ditimpa** (01H hanya menambah; supersede otomatis **DEFER**). UI
  menampilkan "sudah ada dokumen tipe ini" sebagai info.
- Alasan menyalin (bukan mereferensi object staging): modul Dokumen & Foto existing berperilaku identik (hapus/ganti/versi),
  foto memang wajib di prefix foto (`employee_profile.py:173`), dan prefix staging dapat di-purge aman kelak.
  Tidak ada tabel/sistem storage dokumen baru. (Keputusan terbuka Q4 bila user lebih memilih referensi tanpa salin.)
- Salin object dilakukan **sebelum** transaksi DB; bila transaksi gagal → object salinan dihapus (kompensasi). Objek foto
  lama baru dihapus **setelah** commit.

### E. Custom field
- Nilai usulan hanya di `proposed.custom` (JSON submission) sampai HR approve — sudah benar di 01G (terverifikasi di kode:
  router publik tidak pernah menulis `employee_custom_field_values`).
- Saat approve: upsert per `(company_id, employee_id, field_key)` dengan `source_submission_id` = id submission;
  divalidasi ulang dengan `FB.validate_custom` terhadap definisi terkini; definisi nonaktif/terhapus → dilewati & dicatat.
- Tolak/Minta Perbaikan: tidak ada penulisan.
- Custom field tetap **tidak** memengaruhi skor 01F (perilaku 01F existing, sudah diuji 4/4).

### F. Hal tambahan yang ditemukan audit
- **`no_npwp`** (karyawan menyatakan tidak punya NPWP) → bila diterapkan akan menulis `employee_salaries.has_npwp`
  (modul payroll). Rekomendasi: **DEFER apply otomatis**; ditampilkan ke HR sebagai informasi ("tidak diterapkan otomatis —
  sesuaikan di Struktur Gaji bila perlu") dan dicatat di `apply_result`.
- **Perubahan identitas** (`full_name`, `nik`, `birth_date`; flag `identity_change` sudah ada) → faktor verifikasi portal
  ikut berubah. UI wajib menampilkan peringatan + checkbox konfirmasi; NIK dicek unik (`ensure_unique` pola existing).
- **`notes`** karyawan → tampil saja, tidak diterapkan.
- Kolom master yang boleh diterapkan = **hanya** `EDITABLE_FIELDS` (23 field); `status`, `project_id`, jabatan, gaji,
  dll. tidak mungkin tersentuh (whitelist ulang saat apply).

---

## 5. Alur yang diusulkan

```
Karyawan (portal)          HR (Verifikasi Pembaruan Data)                         Sistem
DRAFT ──submit──▶ PENDING_HR_VERIFICATION ──▶ buka detail (Data Saat Ini vs Usulan, konflik, lampiran)
                        │
                        ├─ Setujui ──▶ [transaksi] validasi ulang + cek konflik ulang + apply core/keluarga/custom
                        │              + documents/foto + status APPROVED + open_slot=NULL + audit
                        │              ──▶ (setelah commit) 01F safe_refresh ──▶ completeness_after
                        ├─ Tolak (alasan wajib) ──▶ REJECTED, open_slot=NULL, lampiran REJECTED, audit (tanpa apply)
                        └─ Minta Perbaikan (catatan wajib) ──▶ REVISION_REQUESTED (baris sama, tetap terbuka)
                                 │
Karyawan login portal ◀──────────┘  edit draft yang sama ──submit──▶ PENDING_HR_VERIFICATION (baseline diambil ulang)
Setelah APPROVED/REJECTED: karyawan dapat membuat pengajuan baru (open_slot kosong); form menampilkan keputusan terakhir.
```

Status final:
| Status | Terbuka? | Dapat diedit karyawan | Aksi HR |
|---|---|---|---|
| DRAFT | ya | ya | — (tidak tampil di antrean) |
| PENDING_HR_VERIFICATION | ya | tidak | Setujui / Tolak / Minta Perbaikan |
| REVISION_REQUESTED **(baru)** | ya | ya | — (menunggu karyawan) |
| APPROVED **(baru)** | tidak | tidak | — |
| REJECTED **(baru)** | tidak | tidak | — |

(`CANCELLED` oleh HR/karyawan → DEFER.)

---

## 6. Perubahan schema (minimal, aditif, semua NULL)

Tidak ada tabel baru. Tidak ada kolom baru di `employees`. Tidak ada DROP/RENAME/UPDATE data bisnis.
Migrasi **m0010_hr_verification** (pola ledger m0009) + update `TABLE_SPECS` (startup sync `db.py:1761-1782` juga akan
menambah kolom NULL secara otomatis; migrasi menjaga ledger + grant permission).

| Tabel | Kolom baru | Tipe | Tujuan |
|---|---|---|---|
| `employee_update_submissions` | `reviewed_by` | fk | user HR terakhir yang memutuskan |
| | `reviewed_by_name` | s | nama tampil (audit juga menyimpan) |
| | `reviewed_at` | dt | waktu keputusan terakhir |
| | `review_note` | t | alasan tolak / catatan perbaikan / catatan setuju |
| | `revision_count` | i | jumlah putaran perbaikan |
| | `review_history` | J | ringkas per putaran: `{round, submitted_at, decision, decided_at, reviewer, note, changed_fields}` — **tanpa nilai data** |
| | `apply_result` | J | hasil apply: item diterapkan / dilewati / resolusi konflik / document_id yang dibuat — **tanpa nilai sensitif** |
| | `completeness_after` | J | skor 01F setelah apply (pasangan `completeness_before`) |
| `employee_submission_files` | `document_id` | fk | dokumen resmi hasil promosi |
| | `review_status_at` | dt | waktu PROMOTED/REJECTED |

Nilai status baru (kolom existing `status`): submission `REVISION_REQUESTED/APPROVED/REJECTED`; file `PROMOTED/REJECTED`.
Index: `ix_submission_status` existing cukup untuk volume PT REAL (DEFER index komposit).
Permission baru: `employee_form:verify` (§9).
Alternatif yang **ditolak**: tabel `employee_update_reviews` terpisah (duplikasi dengan audit_logs + kolom di atas;
belum terbukti perlu). Riwayat lengkap tetap di `audit_logs`.

---

## 7. API yang diusulkan (HR, semua `/api`, tenant-scoped, backend authoritative)

Prefix: `/api/employees/update-verifications` (router baru `routers/employee_update_verification.py`).
| Method | Path | Permission | Keterangan |
|---|---|---|---|
| GET | `/summary` | `employee_form:verify` | hitungan per status (Menunggu, Perlu Perbaikan, Disetujui, Ditolak) |
| GET | `/` | `employee_form:verify` | daftar: filter status (default PENDING), project, departemen, cari nama/no. karyawan, rentang tanggal; paging; kolom: no./nama karyawan, project, tanggal submit, status, ringkasan perubahan per section, jumlah lampiran, flag identitas, flag konflik |
| GET | `/{submission_id}` | `employee_form:verify` | detail per section: `current` / `proposed` / `state (OK/ALREADY_APPLIED/CONFLICT)`; keluarga (op + data saat ini vs usulan); custom; lampiran (metadata, tanpa storage key); catatan karyawan; `no_npwp`; completeness before/sekarang; riwayat keputusan; `version` |
| GET | `/{submission_id}/files/{file_id}` | `employee_form:verify` | stream lampiran private (no-store; tanpa storage key) |
| POST | `/{submission_id}/approve` | `employee_form:verify` | body: `{version, resolutions:{item_key: "use_proposed"\|"keep_current"}, confirm_identity?, note?}` |
| POST | `/{submission_id}/reject` | `employee_form:verify` | body: `{version, reason}` (wajib) |
| POST | `/{submission_id}/request-revision` | `employee_form:verify` | body: `{version, note, items?: [item_key]}` (catatan wajib) |

Aturan: semua `extra="forbid"`; body keputusan **tidak menerima nilai data** (tidak ada injeksi field); hanya dari
`PENDING`; `version` + `SELECT FOR UPDATE`; 404 generik lintas tenant; nilai sensitif dimasking kecuali
`can_view_sensitive(ctx)` (aturan Profile 360). Perubahan publik (MODIFY): `OPEN_SUBMISSION_STATUSES` + editable saat
`REVISION_REQUESTED`; `GET /form` mengembalikan `revision {note, items}` dan `last_decision {status, reason, decided_at}`.

---

## 8. UI yang diusulkan (non-teknis, Bahasa Indonesia)

Menu: **Kepegawaian → Verifikasi Pembaruan Data** (`/employees/update-verifications`), badge jumlah "Menunggu".
1. **Daftar**: tab/filter status (Menunggu Verifikasi · Perlu Perbaikan · Disetujui · Ditolak), filter project/departemen,
   cari; kolom: Karyawan (nama + no.), Project, Tanggal Kirim, Status, Ringkasan Perubahan ("Kontak 2 · Bank 1 · Keluarga 1 ·
   Dokumen 2"), badge "Perubahan identitas", badge "Ada konflik". Empty/loading/error state.
2. **Detail review** (halaman/drawer): header karyawan + status + tanggal; ringkasan kelengkapan (sebelum → perkiraan);
   per section kartu tabel 3 kolom **Data Saat Ini | Data Usulan | Keterangan**, baris berubah di-highlight; konflik diberi
   tanda + pilihan "Pakai usulan / Pertahankan data saat ini"; keluarga (Tambah/Ubah/Hapus + alasan); dokumen & foto
   (pratinjau/unduh, info "sudah ada dokumen tipe ini"); pertanyaan tambahan (custom); catatan karyawan; info NPWP
   "tidak diterapkan otomatis".
3. **Aksi** (sticky bar): **Setujui & Terapkan** (dialog konfirmasi + checkbox identitas bila relevan), **Minta
   Perbaikan** (catatan wajib + pilih item), **Tolak** (alasan wajib). Tombol nonaktif bila konflik belum diputuskan.
4. **Riwayat keputusan**: timeline per putaran (dikirim, diminta perbaikan + catatan, dikirim ulang, disetujui/ditolak,
   oleh siapa, kapan).
5. Form publik: banner "Perlu perbaikan" + catatan HR; banner keputusan terakhir (disetujui / ditolak + alasan).
Komponen: Shadcn existing (Table, Tabs, Badge, Dialog, Sheet, Textarea, RadioGroup, Skeleton, Sonner) + komponen baru
`ChangeCompareTable`. Detail visual mengikuti `design_guidelines.md` existing (tanpa desain ulang).

---

## 9. Permission & security

- **Permission baru `employee_form:verify`** ("Verifikasi Pembaruan Data"). Grant default: `tenant_admin` (otomatis semua),
  `company_owner` (wildcard), `hr_admin`, `hr_manager`. Bukan untuk finance/manager/supervisor/employee.
  Alternatif: pakai `employee:edit` (lebih sederhana, tetapi tanpa pemisahan tugas) → keputusan terbuka Q1.
- Tenant: semua query lewat `ctx.tdb` (auto `company_id`); akses id tenant lain → 404 generik.
- Project/data scope: **tidak ada** scope baris HR per project di sistem saat ini (RBAC company-wide). 01H menyediakan
  **filter** project; pembatasan baris per project **DEFER** (butuh infrastruktur lintas modul).
- Sesi publik/karyawan tidak dapat approve: endpoint HR memakai JWT `require_permission`; token sesi publik bukan JWT →
  401. Akan dibuktikan dengan test negatif.
- Backend authoritative: keputusan & resolusi saja yang diterima; nilai yang diterapkan diambil dari `proposed` tersimpan,
  divalidasi ulang (whitelist `EDITABLE_FIELDS`, `FAMILY_EDITABLE`, definisi custom aktif, `validate_field`,
  `FamilyInput`, unik NIK) di dalam transaksi.
- Field terlindungi/sistem (`status`, `project_id`, `company_id`, `id`, jabatan, gaji, role, dll.) tidak dapat diinjeksi:
  tidak ada dalam whitelist dan body keputusan tidak memuat nilai.
- Audit: `employee_update.approved/rejected/revision_requested` (resource `employee_public_form`, record = submission) +
  audit per perubahan master dengan resource `employee` / `document` (muncul di timeline Profile 360) memakai
  `mask_for_audit` (NIK, rekening, NPWP, BPJS dimasking; NIK keluarga dimasking). `review_history`/`apply_result` hanya
  menyimpan nama field, bukan nilai. Tidak ada token/storage key di respons/log.

---

## 10. Strategi konflik (detail teknis)
| Item | Baseline | Pembanding terkini | CONFLICT bila |
|---|---|---|---|
| Field core | `baseline.fields[k]` | `employees[k]` | `norm(current) != norm(baseline)` dan `norm(current) != norm(proposed)` |
| Custom | `baseline.custom[k]` | `employee_custom_field_values` | idem |
| Keluarga update/remove | `baseline.family[ref]` | baris `employee_family_members` | baris berubah (field FAMILY_EDITABLE) atau sudah terhapus |
| Keluarga add | — | anggota existing | peringatan (bukan blok) bila NIK sama / nama+hubungan sama |
| Foto | `photo_version` saat submit (**ditambahkan ke baseline saat submit — MODIFY kecil**) | `employees.photo_version` | berubah |
| Dokumen | — | dokumen tipe sama dibuat setelah `submitted_at` | info saja (tidak menimpa) |
`norm(current) == norm(proposed)` → `ALREADY_APPLIED` (no-op, dicatat). Pemeriksaan diulang di dalam transaksi approve;
bila hasil berbeda dari yang dilihat HR → 409 "Data berubah, muat ulang".
Catatan: submission PENDING yang dibuat sebelum 01H tidak memiliki `baseline.photo_version` → foto diperlakukan "info"
(tidak blok).

---

## 11. Rencana testing (setelah implementasi)
Backend (pytest/httpx, agent + testing agent):
1. Transisi status valid/invalid (hanya dari PENDING; DRAFT/APPROVED/REJECTED → 409); race dua HR → 409 kedua.
2. Approve: core field diterapkan tepat; field non-whitelist tidak berubah; `status/project_id` tak tersentuh; NIK duplikat → 409.
3. Keluarga add/update/remove; ref hilang → konflik.
4. Dokumen → baris `documents` baru (owner_type/owner_id benar), object disalin, file PROMOTED + `document_id`; foto → prefix foto; custom file → referensi.
5. Custom → `employee_custom_field_values` upsert + `source_submission_id`; definisi nonaktif dilewati.
6. Reject → tidak ada perubahan master (hash before/after), file REJECTED, open_slot kosong, karyawan bisa membuat draft baru.
7. Request revision → baris sama, revision_count, karyawan bisa edit & submit ulang, baseline diambil ulang, tidak ada duplikat submission.
8. Konflik: approve tanpa resolusi → 409; dengan `keep_current` → nilai terbaru dipertahankan; `use_proposed` → ditimpa & diaudit.
9. 01F: `completeness_after` terisi & skor berubah sesuai; custom tidak memengaruhi skor.
10. Security: tanpa permission → 403; tenant lain → 404; token sesi publik ke endpoint HR → 401; body dengan nilai/field tambahan → 422; audit tanpa nilai sensitif mentah; respons tanpa storage key.
11. Transaksi: kegagalan di tengah apply → tidak ada perubahan parsial + object salinan dibersihkan.
12. Regresi terarah: 01G public/security/portal, Form Builder, 01F (tanpa suite penuh kecuali diminta).
Frontend (testing agent/Playwright): daftar + filter, detail diff + highlight, konflik blok tombol, approve/reject/revision dengan dialog, riwayat, banner revisi di form publik, responsive 360/1366.
Migrasi: m0010 apply, rerun SKIP, tidak ada drift, grant benar.

---

## 12. Estimasi langkah implementasi
| # | Langkah | Klasifikasi | Estimasi relatif |
|---|---|---|---|
| 1 | m0010 + TABLE_SPECS (kolom aditif, permission `employee_form:verify` + grant) | MODIFY | S |
| 2 | `core/hr_verification.py`: build detail/diff, deteksi konflik, apply transaksional (core, keluarga, custom, dokumen, foto), kompensasi storage | NEW | L |
| 3 | Router HR (summary, list, detail, file, approve/reject/revision) | NEW | M |
| 4 | Public form: status revisi, banner, last_decision, baseline `photo_version` | MODIFY | S |
| 5 | Monitoring Form Builder: hitungan status baru | MODIFY | XS |
| 6 | Backend tests (§11) + regresi terarah | — | M |
| 7 | UI Verifikasi (daftar, detail, compare, aksi, riwayat) + nav/route | NEW/MODIFY | L |
| 8 | UI banner revisi form publik | MODIFY | S |
| 9 | Testing agent E2E + perbaikan | — | M |
| 10 | Dokumentasi progres + plan.md | — | S |
Urutan: 1 → 2 → 3 → 6 (backend hijau) → 4/5 → 7/8 → 9 → 10.

---

## 13. Keputusan terbuka untuk review user
- **Q1 Permission**: `employee_form:verify` baru (disarankan; pemisahan tugas) atau cukup `employee:edit`?
- **Q2 Granularitas**: setuju keputusan per pengajuan + resolusi eksplisit hanya untuk item konflik?
- **Q3 Konflik**: setuju approve diblok sampai tiap konflik diputuskan (Pakai usulan / Pertahankan)?
- **Q4 Dokumen**: salin object ke path resmi (disarankan) atau referensi object staging tanpa salin? Dokumen tipe sama: tambah saja (disarankan) atau arsipkan yang lama?
- **Q5 `no_npwp`**: setuju tidak diterapkan otomatis ke payroll (info saja)?
- **Q6 HR edit nilai usulan**: setuju tidak ada edit di layar verifikasi (koreksi via Minta Perbaikan / Profile 360)?
- **Q7 Scope project**: setuju filter project saja; pembatasan baris per project DEFER?
- **Q8 Notifikasi**: setuju notifikasi email/in-app ke karyawan DEFER?

## 14. DEFER (di luar 01H)
Approval multi-level via `approval_workflows` · scope baris per project · notifikasi karyawan · supersede/arsip otomatis
dokumen lama · purge/retensi lampiran REJECTED/removed · batas jumlah revisi · CANCELLED · edit nilai oleh HR ·
apply `no_npwp` ke payroll · 01I/01J/payroll/recruitment/attendance.

## 15. Catatan data staging (read-only)
Saat ini di staging: `employee_update_submissions` = 1 baris `PENDING_HR_VERIFICATION` (dibuat sebelum 01H, tidak
disentuh); `employee_submission_files` active = 3 DOCUMENT + 1 PHOTO; `employee_custom_field_values` = 0; karyawan aktif = 94.
Submission PENDING lama tetap dapat diproses 01H (baseline tersedia; hanya `photo_version` baseline yang belum ada → info).

## 16. Catatan Git
Branch lokal baru `feature/upgrade-01h-hr-verification` dibuat dari HEAD lokal (berisi auto-commit platform `9b54a61`:
test report + `.gitignore`) agar file 01H tidak mendarat di branch PR #16. Ref lokal `feature/upgrade-01g-form-builder`
dikembalikan ke `70634e7` (= remote PR #16). Tidak ada push. Saat PR 01H kelak, auto-commit platform harus dibersihkan
dari riwayat branch (dengan persetujuan user).
