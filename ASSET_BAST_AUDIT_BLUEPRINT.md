# PHASE 2A — ASSET & BAST CONTROL · STEP 1: AUDIT EXISTING + BLUEPRINT

Status: **AUDIT ONLY** — tidak ada kode, migration, tabel, endpoint, UI, commit, push, PR, merge, atau deploy.
Production Changed: **NO** · Baseline: 01I LOCKED (lokal `89666b2` + `17e9080`), 01H di PR #17 (belum merge).
Tanggal audit: 2026-09-28 · Repo: `/app/.repo_work/Payroll` (identik dengan `/app` untuk file aplikasi).

Klasifikasi: **REUSE** (pakai apa adanya) · **MODIFY** (perluas komponen existing) · **NEW** (buat baru) · **DEFER** (fase berikut).

---

## 0. Ringkasan eksekutif

1. **Tidak ada fondasi Asset/Inventaris/GA/BAST sama sekali** di aplikasi: tidak ada tabel, model, router, permission,
   module key, menu, halaman, maupun placeholder. Grep `asset|inventar|inventory|bast|serial_number` di backend/frontend
   hanya menemukan *branding assets* (logo/favicon platform) dan kata "maintenance" sebagai kategori lembur / nama divisi seed
   — **tidak terkait**. Jadi **tidak ada risiko membuat "modul Asset kedua"**.
2. Modul `mobilization` dan `finance_request` hanya berstatus **planned** (izin RBAC + teks deskripsi UI). Tidak ada tabel
   maupun router, dan tidak memuat penyerahan APD/seragam/alat. **Tidak dapat direuse sebagai Asset.**
3. Banyak **building block lintas modul yang matang dan dapat direuse**: engine master generik, RBAC berbasis konfigurasi,
   dokumen polimorfik + storage R2, audit log, pola impor Core HR (NEW/UPDATE/UNCHANGED/CONFLICT/ERROR + hash commit),
   PDF reportlab (slip gaji), pola "maks 1 ACTIVE" + row-lock dari 01D, pola kategori sistem + status configurable dari
   01B, engine scope 01I, dan pola tab Profil 360.
4. Yang **harus NEW**: modul `asset`, tabel master aset + transaksi + kepemilikan (holding) + histori event + BAST,
   **engine penomoran dokumen generik** (belum ada; setiap nomor saat ini dibuat manual per fitur dan berbasis `count`,
   tidak aman terhadap balapan), serta impor khusus aset.

---

## A. Audit database / model

### A.1 Tabel terkait Asset — hasil: TIDAK ADA

| Topik | Tabel/model existing | Status |
|---|---|---|
| asset / inventory | — | BELUM ADA |
| kategori / satuan / status / kondisi aset | — | BELUM ADA |
| asset assignment / holder | — | BELUM ADA |
| asset movement / history | — | BELUM ADA |
| pengembalian | — | BELUM ADA |
| BAST | — | BELUM ADA |
| maintenance | — (hanya `timekeeping.py:157` kategori lembur "Pemeliharaan") | BELUM ADA / tidak terkait |
| employee asset | — | BELUM ADA |

### A.2 Tabel existing yang relevan untuk direuse

Skema dideklarasikan di `backend/app/core/db.py`. Setiap tabel otomatis mendapat kolom `MASTER` standar (id UUID,
company_id, status, created/updated_at/by), dan sinkronisasi skema aditif terjadi saat startup. Migration berupa
`backend/migrations/m00xx_*.py` yang idempoten dan tercatat di ledger `schema_migrations`.

| Tabel | Field penting | Relasi / index | Scope tenant | Dipakai? | Peran untuk Asset | Klasifikasi |
|---|---|---|---|---|---|---|
| `projects` (`db.py:277`) | code, name, client_name, branch_id, **work_location_id**, cost_center_id, start/end_date | FK branch, work_location, cost_center; unique code per company | company_id | Operasional (master + 01D + 01I) | Lokasi project aset / transaksi | **REUSE** |
| `work_locations` (`masters.py:24`) | code, name, branch_id, address, lat/long, geofence | FK branch | company_id | Operasional | Lokasi kerja aset | **REUSE** |
| `employees` | employee_number (NIK karyawan), full_name, status, project_id (mirror) | — | company_id | Operasional | Pemegang aset; validasi impor | **REUSE** |
| `employee_assignments` (`db.py:431`, index `db.py:770`) | employee_id, project_id, work_location_id, start/end_date, assignment_status ACTIVE/ENDED, source, reason, previous_assignment_id | idx (company, employee, status), (company, status, project, employee) | company_id | Operasional (01D, sumber scope 01I) | **Pola** kepemilikan "maks 1 ACTIVE" + riwayat tidak ditimpa | **REUSE pola** (tabel tidak dipakai untuk aset) |
| `documents` (`db.py:289`, idx `ix_documents_owner` `db.py:723`) | document_type_id, **owner_type**, **owner_id**, owner_label, document_number, file_*, storage_path, version, is_deleted | polimorfik (company, owner_type, owner_id) | company_id | Operasional (employee, company, applicant) | Lampiran aset, foto kondisi, **BAST bertanda tangan** | **MODIFY** (tambah owner_type `asset`, `asset_transaction`, `asset_bast` + aturan scope) |
| `document_types` (master) | code, name, allowed_extensions, … | — | company_id | Operasional | Tipe "BAST Penyerahan / Pengembalian / Foto Kondisi" | **REUSE** (data konfigurasi) |
| `company_settings` (`db.py:251`) | employee_id_prefix, employee_id_next_number, date_format | — | company_id | Operasional | Tempat pola nomor karyawan; **bukan engine generik** | REUSE sebagian / lihat §G.3 |
| `employee_import_batches` / `_rows` (`db.py:~450`) | batch status, row_class, hash file, payload, commit_status | idx company+created_at | company_id | Operasional (01C) | **Pola** impor aset | **REUSE pola** (tabel khusus karyawan) |
| `approval_workflows` / `approval_steps` (`db.py:325`) + snapshot per `document_kind` (`db.py:851`) | workflow per jenis dokumen | unique (company, document_kind, record_id, round, step) | company_id | Operasional (cuti/lembur/absensi/rekrutmen) | Opsional: approval penyerahan | **DEFER** |
| `audit_logs` | action, resource, record_id, record_label, before/after, module, notes | — | company_id | Operasional | Jejak audit semua aksi aset | **REUSE** |
| `user_data_scopes` / `_items` (01I) | mode ALL_TENANT / SELECTED_PROJECTS, item project | per (company, user) | company_id | Operasional | Enforcement scope aset | **REUSE** |
| `employee_status_history` + kategori status 01B (`core/employee_status.py:20` ACTIVE/STANDBY/INACTIVE) | histori status append-only | — | company_id | Operasional | Hook Exit Clearance di masa depan | **REUSE** (hook, DEFER implementasi) |

**Kesimpulan A:** skema aset harus **NEW**. Master lokasi, karyawan, dokumen, audit, dan scope **REUSE**.

---

## B. Audit backend

| Kebutuhan | Temuan | Status |
|---|---|---|
| Router Asset / Inventory / GA | Tidak ada di `backend/app/routers/` | BELUM ADA |
| CRUD master aset | — | BELUM ADA |
| Master kategori / satuan / kondisi / status | — (tetapi engine master generik tersedia: `backend/app/masters.py` + `routers/master.py` prefix `/api/master/{resource_path}`: list/get/create/update/delete/options, unique code, relasi FK, cek referensi sebelum hapus) | Engine: **SUDAH OPERASIONAL**; master aset: BELUM ADA |
| Penyerahan / pengembalian / mutasi / histori pemegang | — (pola sejenis: 01D `core/assignment.py`, maks 1 ACTIVE dengan row-lock, riwayat ENDED tidak ditimpa) | BELUM ADA (pola **OPERASIONAL**) |
| Upload attachment | `routers/documents.py` (POST `/api/documents`, owner polimorfik, `OWNER_TYPES` `documents.py:22` = company, employee, applicant), storage R2 `core/storage.py` (path tenant `companies/{cid}/documents/...`, presigned URL) | **OPERASIONAL** — perlu MODIFY owner_type |
| BAST | — | BELUM ADA |
| PDF generation | `core/pdf.py` reportlab (`_styles`, `_kv_table`, `_amount_table`, `build_payslip_pdf`), dipakai `routers/payroll.py:845`; logo tenant ada (`routers/companies.py:208`, `branding_assets.py`) | **OPERASIONAL** (payslip) — REUSE helper untuk BAST |
| Penomoran dokumen | Per fitur, manual: `core/employee_numbering.py:16` (atomic `$inc` di company_settings, tanpa reset tahunan), `routers/contracts.py:328` & `routers/recruitment.py:122` (**berbasis `count_documents` + loop cek** → rawan tabrakan saat bersamaan; mengandalkan unique index). Tidak ada tabel sequence generik maupun format configurable | **FOUNDATION parsial** → NEW engine |
| Approval | `approval_workflows` + snapshot per `document_kind` (`core/time_approval.py`, `recruitment_workflow.py`) | OPERASIONAL untuk modul lain; aset **DEFER** |
| Import | `core/employee_import.py` + `routers/employee_import.py`: template → upload/analyze (read-only) → preview rows → commit ulang dengan **hash file wajib sama** → riwayat batch; kelas `NEW, UPDATE, UNCHANGED, CONFLICT, ERROR` (`employee_import.py:46`); per baris transaksional; restricted 01I → 403 | **OPERASIONAL** (khusus karyawan) → REUSE **pola**, NEW implementasi aset |
| Export | openpyxl per router (`core/excel.py`, `core/time_excel.py`); tidak ada helper export generik; 01I: `full_scope_dependency` | OPERASIONAL (pola) |
| Audit log | `core/audit.py:33` `log_action(ctx, action, resource, record_id, record_label, before, after, module, company_id, notes)` | **OPERASIONAL** — REUSE |
| Permission / RBAC | `core/rbac.py:33` `RESOURCES{key: (label, module, actions)}`, `MODULES` `rbac.py:88`, `ROLES` `rbac.py:100`, `default_role_permissions()`; matriks dapat diedit via DB (`role_permissions`); `deps.require_permission(resource, action, module_key, self_service)` | **OPERASIONAL** — MODIFY (tambah modul/resource aset) |
| Data scope 01I | `core/data_scope.py`: `get_scope`, `allowed_project_ids`, `with_scope`, `employee_in_scope`, `assert_employee_visible` (404), `require_full_scope` / `full_scope_dependency` (403); `UNSCOPED_MODULES` di `deps.py` untuk modul yang belum scope-aware | **OPERASIONAL** — REUSE (aset dibangun scope-aware sejak awal, **tidak** dimasukkan ke UNSCOPED_MODULES) |

---

## C. Audit frontend

| Item | Temuan |
|---|---|
| Menu Asset / Inventaris / GA / BAST / Asset Karyawan | **Tidak ada.** `frontend/src/lib/nav.js` berisi grup: Platform, Ringkasan, Organisasi, Data Referensi (`nav.js:79`), Konfigurasi, Kepegawaian (`nav.js:101`), Payroll & Pajak, Dokumen, dan modul waktu/rekrutmen |
| Route/page/form terkait | **Tidak ada.** `App.js` tidak memiliki route aset |
| Placeholder modul | `lib/moduleFoundation.js` hanya untuk `mobilization` (`:47`) dan `finance_request` (`:58`), berisi teks alur tanpa fungsi. **Tidak ada entri aset** |
| Komponen reusable | `pages/MasterDataPage.jsx` (halaman master generik), `components/common/DataTable.jsx`, `ConfirmDialog`, layout modul (`pages/leave/LeaveOvertimeModuleLayout.jsx`, `pages/attendance/AttendanceModuleLayout.jsx`), wizard impor karyawan (01C), `components/access/DataScopeBadge.jsx` (01I), uploader dokumen |

**Yang user bisa lakukan saat ini terkait aset: tidak ada.** Paling jauh, user dapat mengunggah file bebas ke Arsip Dokumen
(owner karyawan/perusahaan) tanpa struktur aset, kepemilikan, status, atau BAST.

---

## D. Audit Employee Profile 360

- `frontend/src/pages/EmployeeDetailPage.jsx:676-688`: tab summary, personal, family, employment, placement, bank, bpjs,
  documents(n), contracts(n), certifications(n), history, payroll (kondisional). Pola: `TabsTrigger` + `TabsContent` +
  komponen di `components/employees/*`. Data dimuat dari loader detail (`data.documents`, `data.contracts`, …).
- **Belum ada tab/area Aset.** Pola tab **dapat diperluas tanpa refactor** (MODIFY): tambah tab **"Aset (n)"** yang berisi
  (1) aset yang sedang dipegang, (2) histori aset, (3) daftar BAST + unduh PDF / salinan bertanda tangan, (4) dokumen aset.
  Tab dimuat lazy lewat endpoint aset tersendiri, bukan dari loader detail, agar profil tidak melambat.
- Kelengkapan 01F (`core/completeness_mapping.py:28`) **tidak** perlu kategori aset (DEFER / tidak perlu).
- Indikator "Aset outstanding: n" di Ringkasan disiapkan untuk Exit Clearance (lihat §P).

---

## E. Fitur yang dapat REUSE (daftar konsolidasi)

| # | Komponen | Lokasi | Pemakaian di Asset | Klas. |
|---|---|---|---|---|
| 1 | Engine master generik | `masters.py`, `routers/master.py`, `MasterDataPage.jsx` | Kategori, Satuan, Kondisi (config-only) | **REUSE** |
| 2 | Pola status configurable + kategori sistem (01B) | `core/employee_status.py`, `routers/employee_status.py` | Status aset configurable yang dipetakan ke **kategori sistem lifecycle** | **REUSE pola** |
| 3 | Pola maks 1 ACTIVE + row-lock + riwayat ENDED (01D) | `core/assignment.py` | Holding aset (1 aset = maks 1 pemegang aktif) | **REUSE pola** |
| 4 | Dokumen polimorfik + R2 | `routers/documents.py`, `core/storage.py` | Foto kondisi, lampiran, BAST ditandatangani | **MODIFY** (owner_type baru + scope) |
| 5 | PDF reportlab | `core/pdf.py` | `build_bast_pdf` | **REUSE helper** |
| 6 | Logo & profil tenant | `routers/companies.py`, `branding_assets.py` | Kop BAST | **REUSE** |
| 7 | Pola impor Core HR | `core/employee_import.py` | Impor Master Aset + Saldo Awal Pemegang | **REUSE pola** |
| 8 | openpyxl export | `core/excel.py` | Export aset/histori/BAST | **REUSE pola** |
| 9 | Audit log | `core/audit.py` | Semua aksi | **REUSE** |
| 10 | RBAC config | `core/rbac.py` | Modul + resource aset | **MODIFY** |
| 11 | Scope 01I | `core/data_scope.py` | Filter project aset/transaksi/BAST/export | **REUSE** (+ helper kecil generik "filter by project column") |
| 12 | Tab Profil 360 | `EmployeeDetailPage.jsx` | Tab Aset | **MODIFY** |
| 13 | Layout modul + nav | `nav.js`, `*ModuleLayout.jsx`, `App.js` | Modul "Aset & BAST" | **MODIFY** |
| 14 | `tx.select_one_for_update` | `core/db.py:1859` | Lock aset & sequence | **REUSE** |

---

## F. Gap terhadap kebutuhan PT REAL

| Kebutuhan | Kondisi existing | Klas. |
|---|---|---|
| Master Aset (kode, nama, kategori, satuan, merk, tipe, SN, perolehan, nilai, project, lokasi, kondisi, status, keterangan) | Tidak ada | **NEW** |
| Master kategori / satuan / kondisi configurable | Engine master ada, entri belum | **NEW (config)** |
| Status configurable tetapi lifecycle aman | Pola 01B ada | **NEW (reuse pola)** |
| 1 kode = 1 unit fisik | — | **NEW (aturan)** |
| Lifecycle + larangan A→B langsung | — | **NEW** |
| Penyerahan / Pengembalian / Pemeriksaan GA | — | **NEW** |
| BAST dokumen output + PDF + salinan bertanda tangan | PDF & dokumen ada | **NEW + REUSE** |
| Dual numbering (sistem + manual) | Tidak ada engine sequence | **NEW** |
| Histori tidak di-overwrite | Pola 01D ada | **NEW (reuse pola)** |
| Impor Master Aset + Saldo Awal Pemegang | Pola 01C ada | **NEW (reuse pola)** |
| Export 7 jenis + filter + scope | Pola ada | **NEW** |
| Scope 01I pada semua jalur | Engine ada | **REUSE** |
| Tab aset Profil 360 | Pola tab ada | **MODIFY** |
| Exit Clearance | Tidak ada fitur offboarding | **DEFER** (siapkan helper outstanding) |
| Inventaris bulk / consumable (stok qty) | Tidak ada | **DEFER** (modul terpisah) |
| Maintenance work order | Tidak ada | **DEFER** (cukup status/disposisi Maintenance) |
| Approval penyerahan | Engine ada untuk modul lain | **DEFER** (opsional) |
| Depresiasi / akuntansi aset | Modul accounting planned | **DEFER** |

---

## G. Desain Master Asset (target)

### G.1 Master configurable (engine master generik — **REUSE**, entri **NEW**)

| Master | resource_path | Field | Catatan |
|---|---|---|---|
| Kategori Aset | `asset-categories` | code, name, description, `requires_serial_number` (b), `code_prefix` (opsional, untuk kode otomatis), `default_unit_id` | Contoh: Laptop, Handphone, Kendaraan, Kamera, Alat Kerja |
| Satuan Aset | `asset-units` | code, name, description | **Hanya label informasi**; contoh seed: Unit, Pcs, Set, Pasang, Buah, Paket. Tenant bebas menambah; **tidak hardcode** |
| Kondisi Aset | `asset-conditions` | code, name, `is_usable` (b), `severity` (i), description | Contoh: Baik, Baik–Lecet Ringan, Rusak Ringan, Rusak Berat, Hilang |
| Status Aset | `asset-statuses` | code, name, **`system_category`** (wajib, enum sistem), description | Pola 01B: label bebas, perilaku dari kategori sistem (§H) |

Master memakai `unique: ["code"]` per company, soft-delete / aktif-nonaktif, dan cek referensi sebelum hapus (`refs` → `assets`).
Satu set default disemai per tenant saat modul diaktifkan, dan tenant dapat mengubahnya.

### G.2 Tabel `assets` (**NEW**)

| Field | Tipe | Aturan |
|---|---|---|
| id, company_id, status (record), audit fields | MASTER | standar |
| `asset_code` | s64 | **unik per company**; input manual atau otomatis dari sequence `ASSET` (prefix kategori opsional) |
| `name` | s | wajib |
| `category_id` → asset_categories | fk | wajib |
| `unit_id` → asset_units | fk | wajib; **informasi saja, bukan qty** |
| `brand`, `model` | s | opsional |
| `serial_number` | s | wajib jika kategori `requires_serial_number`; **unik per company bila diisi** (kolom normalisasi upper/trim + unique index; NULL boleh berganda) |
| `acquisition_date` (s32) / `acquisition_year` (i) | | salah satu; tanggal lengkap diutamakan |
| `acquisition_value` | decimal | opsional; tampil/ekspor hanya bagi yang punya izin `asset.view_value` (sensitif) |
| `project_id` → projects, `work_location_id` → work_locations | fk | **lokasi "rumah" / penempatan saat ini** |
| `condition_id` → asset_conditions | fk | kondisi terakhir hasil pemeriksaan |
| `status_id` → asset_statuses | fk | label status |
| `lifecycle_state` | s32 | **kolom sistem otoritatif** (READY, IN_USE, PENDING_INSPECTION, MAINTENANCE, DAMAGED, LOST, DISPOSED); hanya diubah oleh engine transaksi |
| `current_holding_id` | fk | denormalisasi cepat (sumber otoritatif tetap `asset_holdings`) |
| `notes` | t | keterangan |
| `row_version` | i | optimistic concurrency |

Index: `uq(company_id, asset_code)`, `uq(company_id, serial_number_norm)`, `(company_id, project_id, lifecycle_state)`,
`(company_id, category_id)`, `(company_id, work_location_id)`.

### G.3 Aturan identitas: 1 Kode Asset = 1 Unit Fisik

- Tidak ada kolom `quantity` di `assets`. Satuan hanya label.
- Impor/form menolak baris yang mencoba memakai satu kode untuk banyak SN.
- **Inventaris bulk (consumable/stok qty): DEFER**. Rekomendasi: modul terpisah di masa depan (`inventory_items` +
  `inventory_ledger` berbasis qty), **tidak mencampur lifecycle aset individual**. Tidak ada konsep bulk existing yang perlu
  diselaraskan.

---

## H. Desain Lifecycle Asset (**NEW**)

Kategori sistem (`lifecycle_state`), tidak dapat diubah tenant:

```
READY ──Penyerahan──▶ IN_USE ──Pengembalian──▶ PENDING_INSPECTION ──Pemeriksaan GA──▶ READY
                                                                   ├──▶ MAINTENANCE ──(selesai)──▶ READY
                                                                   ├──▶ DAMAGED ──▶ (MAINTENANCE / DISPOSED)
                                                                   ├──▶ LOST
                                                                   └──▶ DISPOSED (terminal)
```

Hard rules (engine backend, bukan UI):
1. **Maks 1 active holder per aset**: row-lock aset (`select_one_for_update`) ditambah kolom `active_lock` pada `asset_holdings`
   (= asset_id saat ACTIVE, NULL saat ENDED) dengan **unique (company_id, active_lock)**. MariaDB mengizinkan NULL berganda,
   jadi constraint ini dijaga database, bukan hanya aplikasi.
2. **Penyerahan hanya dari READY.** IN_USE / PENDING_INSPECTION / MAINTENANCE / DAMAGED / LOST / DISPOSED → 409.
3. **Tidak ada A→B langsung.** Tidak ada endpoint "transfer/mutasi pemegang". Alurnya harus Return(A) → Pemeriksaan →
   READY → Handover(B).
4. Pengembalian hanya untuk holding ACTIVE. Pemeriksaan hanya dari PENDING_INSPECTION.
5. "Mutasi lokasi" untuk aset **READY** (pindah gudang/project tanpa pemegang) = transaksi `RELOCATION` tercatat di histori.
   Aset IN_USE tidak dimutasi lokasinya tanpa return.
6. Semua transisi menulis event append-only (§L) + audit log. Tidak ada UPDATE/DELETE histori.
7. Status label (`status_id`) otomatis disetel ke status default dari kategori sistem terkait. Tenant boleh punya beberapa
   label per kategori (mis. "Siap Pakai – Gudang Pusat").

---

## I. Desain Penyerahan & Pengembalian (**NEW**)

### I.1 `asset_transactions` (header) + `asset_transaction_lines` (per aset)

Satu transaksi dapat memuat **beberapa aset untuk satu karyawan** (mis. laptop + charger + HP), dengan satu BAST.

Header: `transaction_type` (HANDOVER, RETURN, INSPECTION, RELOCATION, OPENING_BALANCE), `transaction_number` (sequence
internal), `employee_id`, `project_id`, `work_location_id`, `transaction_date`, `ga_pic_user_id` (PIC GA / pemeriksa),
`notes`, `state` (DRAFT → COMPLETED / CANCELLED), `source` (UI / IMPORT), `related_transaction_id` (return → handover asal).

Lines: `asset_id`, `condition_id` (kondisi awal saat serah / kondisi saat kembali / hasil periksa), `accessories` (teks atau
JSON checklist kelengkapan), `damage_notes`, `result_state` (untuk INSPECTION: READY / MAINTENANCE / DAMAGED / LOST /
DISPOSED), `holding_id`.

### I.2 Penyerahan (HANDOVER)

Isi: employee, aset (1..n), project, lokasi, tanggal serah, kondisi awal per aset, kelengkapan, PIC GA, catatan,
lampiran (dokumen owner `asset_transaction`), BAST Penyerahan.

Validasi:
- aset READY + dalam scope;
- karyawan status kategori ACTIVE (bukan INACTIVE) dan dalam scope;
- project transaksi dalam scope; lokasi valid milik company;
- satu transaksi DB: lock semua aset → buat holding ACTIVE → aset IN_USE + project/lokasi mengikuti transaksi → event → audit.

### I.3 Pengembalian (RETURN)

Isi: tanggal kembali, kondisi saat kembali, kelengkapan, kerusakan/catatan, pemeriksa GA, lampiran/foto, BAST Pengembalian.

Efek: holding → ENDED (end_date, return_transaction_id), aset → **PENDING_INSPECTION**, event, audit.

### I.4 Pemeriksaan GA (INSPECTION)

Bisa langsung dalam form pengembalian (checkbox "sekaligus diperiksa") atau terpisah. Hasil per aset: READY / MAINTENANCE /
DAMAGED / LOST / DISPOSED + kondisi final.

### I.5 `asset_holdings` (**NEW**, pola 01D)

`asset_id`, `employee_id`, `project_id`, `work_location_id`, `start_date`, `start_date_known` (b, untuk saldo awal),
`end_date`, `holding_status` ACTIVE/ENDED, `source` (HANDOVER / OPENING_BALANCE), `handover_transaction_id`,
`return_transaction_id`, `condition_out_id`, `condition_in_id`, `active_lock` (unique).
Index: `(company_id, employee_id, holding_status)`, `(company_id, asset_id, start_date)`, `(company_id, project_id, holding_status)`.

---

## J. Desain BAST — Nomor Sistem + Nomor Manual (**NEW**)

BAST = **dokumen output** dari transaksi (bukan transaksi utama). Alur: **Transaksi COMPLETED → Generate BAST → Preview →
PDF → Upload Signed Copy**.

### J.1 `asset_bast_documents`

| Field | Aturan |
|---|---|
| `transaction_id` | wajib (HANDOVER / RETURN / OPENING_BALANCE) |
| `bast_type` | HANDOVER, RETURN, EXISTING_CONFIRMATION, EXISTING_REFERENCE (BAST manual lama hasil impor) |
| **`system_number`** | otomatis, **unik per company** (`uq(company_id, system_number)`), **immutable**; hanya dapat di-VOID, lalu diganti nomor baru |
| **`manual_number`** | opsional, input user (mis. `023/GA/REAL/IX/2026`); index `(company_id, manual_number)` untuk cari/filter. **Tidak unik secara keras** (dokumen lama bisa ganda); duplikat → peringatan, bisa diperketat per kebijakan tenant |
| `bast_date` | tanggal dokumen |
| `doc_state` | DRAFT → GENERATED → SIGNED; VOID (dengan alasan) |
| `generated_pdf_path` | PDF sistem di R2 (versi); regenerasi hanya saat belum SIGNED |
| `signed_document_id` | → `documents` (owner_type `asset_bast`) |
| `snapshot` (JSON) | salinan data saat generate (pihak, aset, kondisi, kelengkapan) agar PDF historis tidak berubah bila master berubah (pola snapshot keputusan 01H) |

Nomor manual lama **tidak pernah ditimpa**. Sistem tetap memberi `system_number` sendiri berdampingan.
Keduanya tampil, dapat dicari, difilter, dan diekspor.

### J.2 Engine penomoran generik `document_sequences` (**NEW**)

Existing: tidak ada engine; pola `count_documents` di kontrak/kandidat **tidak aman terhadap balapan** (catat sebagai risiko,
jangan ditiru).

Tabel: `company_id`, `sequence_key` (BAST_HANDOVER, BAST_RETURN, BAST_EXISTING, ASSET_CODE, ASSET_TXN), `period_key`
(mis. `2026`, atau `ALL` bila tanpa reset), `next_value`, `format` (mis. `BAST-AST/{YYYY}/{SEQ:6}`,
`BAST-RTN/{YYYY}/{SEQ:6}`), `reset_policy` (YEARLY / NEVER).

Alokasi: `SELECT … FOR UPDATE` di dalam transaksi yang sama dengan pembuatan BAST, plus unique index sebagai jaring pengaman.
Format dapat dikonfigurasi di Pengaturan Aset (izin `asset_config.config`). Engine ini generik sehingga modul lain (kontrak,
kandidat) dapat **dimigrasikan belakangan** (**DEFER**, di luar scope 2A).

### J.3 PDF (**REUSE** `core/pdf.py`)

`build_bast_pdf(snapshot, company)`: kop (logo + profil tenant), judul per tipe, nomor sistem + nomor manual (jika ada),
pihak pertama (PIC GA) / pihak kedua (karyawan: nama, NIK karyawan, jabatan, project, lokasi), tabel aset (kode, nama, merk/
tipe, SN, satuan, kondisi, kelengkapan), catatan, kolom tanda tangan. Template kalimat per tipe disimpan di pengaturan
tenant (teks pembuka/penutup configurable; **DEFER** untuk editor template kaya).

---

## K. Desain Impor (**NEW**, pola 01C **REUSE**)

Alur: **Download Template → Upload → Analyze (read-only) → Preview → Validate → Commit (file hash wajib sama) → Riwayat Impor**.
Kelas baris: **NEW, UPDATE, UNCHANGED, CONFLICT, ERROR**. **Tidak ada silent overwrite**: UPDATE hanya untuk field yang berbeda
dan ditampilkan per field. CONFLICT tidak pernah di-commit.

Tabel: `asset_import_batches`, `asset_import_rows` (`import_type`: ASSET_MASTER / OPENING_HOLDING). Struktur disalin dari
tabel impor karyawan; engine karyawan tidak digeneralisasi sekarang (**DEFER** refactor generik).

### K.1 Impor 1 — Master Asset

Kolom: Kode Asset, Nama Asset, Kategori, Satuan, Merk, Tipe/Model, Serial Number, Tanggal/Tahun Perolehan, Nilai Perolehan,
Project, Lokasi Kerja, Kondisi, Status, Keterangan.

- Kategori/Satuan/Kondisi/Status dicocokkan **by code atau nama persis** dengan master. Tidak ditemukan → **ERROR**
  (tidak membuat master otomatis; opsi "buat master baru" = DEFER).
- NEW: kode belum ada. UPDATE: kode ada dan ada field berbeda. UNCHANGED: identik.
- CONFLICT: kode duplikat dalam file; SN duplikat (dalam file / dengan aset lain); SN wajib kategori kosong; mengubah
  project/lokasi aset yang sedang IN_USE; mengubah status ke kategori yang melanggar lifecycle (mis. set READY padahal ada
  holder aktif); company mismatch.
- Impor master **tidak pernah** membuat holding. Status yang diizinkan saat impor: READY / MAINTENANCE / DAMAGED / LOST /
  DISPOSED. IN_USE hanya lewat Impor 2.

### K.2 Impor 2 — Asset Existing di Karyawan (Saldo Awal / Penempatan Existing)

Kolom: Kode Asset, Nomor Induk Karyawan, Nama Karyawan (validasi), Tanggal mulai pegang (opsional), Project, Lokasi,
Kondisi, Kelengkapan, Nomor BAST Manual/Existing, Catatan.

Validasi / CONFLICT:
- aset tidak ditemukan;
- aset sudah punya active holder;
- aset bukan READY;
- NIK tidak ditemukan;
- nama tidak cocok dengan NIK (fuzzy normalisasi → CONFLICT, bukan ERROR, agar dapat dikoreksi);
- karyawan INACTIVE;
- project/lokasi tidak ditemukan;
- satu aset muncul dua kali di file;
- di luar scope 01I.

Commit per baris (transaksional):
- `asset_transactions` type **OPENING_BALANCE**, `source=IMPORT`, state COMPLETED, tanggal = tanggal impor (**bukan**
  tanggal lama);
- `asset_holdings` source **OPENING_BALANCE**, `start_date` = tanggal mulai jika diketahui, `start_date_known=false` bila
  kosong;
- event histori `OPENING_BALANCE` berketerangan "Saldo Awal — Penempatan Existing (impor)".
  **Tidak** dibuat event HANDOVER palsu atau tanggal serah fiktif.
- Jika ada nomor BAST manual: `asset_bast_documents` bast_type **EXISTING_REFERENCE**, `manual_number` disimpan, `system_number`
  dialokasikan (seri BAST_EXISTING), tanpa PDF sistem. Scan BAST lama dapat diunggah sebagai signed copy.
- Jika tidak ada BAST lama: dapat dibuat **BAST Konfirmasi Existing** (bast_type EXISTING_CONFIRMATION) secara massal atau per
  karyawan → PDF sistem → ditandatangani → unggah.

---

## L. Histori Asset (**NEW**) — `asset_events` append-only

Field: `asset_id`, `event_type` (CREATED, UPDATED_MASTER, OPENING_BALANCE, HANDOVER, RETURN, INSPECTION, RELOCATION,
STATUS_CHANGE, BAST_GENERATED, BAST_SIGNED, BAST_VOID, IMPORTED), `event_at`, `actor_user_id`, `from_state` / `to_state`,
`employee_id`, `project_id`, `work_location_id`, `condition_id`, `transaction_id`, `holding_id`, `bast_id`,
`system_number` / `manual_number` (snapshot), `notes`.
Index: `(company_id, asset_id, event_at)`, `(company_id, employee_id, event_at)`.

Pertanyaan bisnis yang terjawab: pemegang saat ini (holding ACTIVE); pemegang sebelumnya (holding ENDED); project/lokasi
yang pernah ditempati (events); tanggal serah/kembali, kondisi keluar/kembali (holdings + lines); nomor BAST sistem/manual;
lampiran (documents per transaksi/BAST).
**Tidak ada endpoint update/delete event.** Koreksi dilakukan dengan event koreksi baru.

---

## M. Desain Export (**NEW**, openpyxl)

| Export | Isi |
|---|---|
| Master Asset | seluruh field master + lifecycle + pemegang saat ini |
| Asset Dipakai | holding ACTIVE: aset, karyawan, NIK, project, lokasi, tanggal mulai (+ flag saldo awal), kondisi keluar, BAST sistem/manual |
| Asset per Karyawan | filter employee |
| Per Project / Per Lokasi | filter project / lokasi |
| Histori Asset | asset_events rentang periode |
| Daftar BAST | nomor sistem, nomor manual, tipe, tanggal, karyawan, aset, doc_state, ada signed copy |

Filter: Project, Lokasi, Kategori, Satuan, Status, Kondisi, Employee, Periode.
**01I:** export dibangun scope-aware (query memakai `allowed_project_ids`). Kalau filter scope belum siap di iterasi awal,
export wajib `full_scope_dependency` (403 untuk restricted), sesuai prinsip fail-closed 01I. **Tidak boleh tenant-wide untuk
restricted.**

---

## N. Integrasi Employee Profile 360 (**MODIFY**)

- Tab baru **"Aset (n)"** di `EmployeeDetailPage.jsx`, dengan komponen `components/employees/AssetTab.jsx`:
  1. Sedang dipegang (kartu: kode, nama, SN, sejak, sumber Saldo Awal/Penyerahan, BAST);
  2. Histori (holding ENDED);
  3. BAST (unduh PDF / signed copy);
  4. tombol "Serahkan Aset" dan "Kembalikan" bila berizin, menuju form modul Aset (prefill karyawan).
- Endpoint: `GET /api/employees/{id}/assets` (assert_employee_visible → 404 bila di luar scope).
- Ringkasan: badge "Aset outstanding: n".

---

## O. Integrasi Project / Lokasi / 01I (**REUSE**)

- Scope aset **berbasis project aset** (`assets.project_id`), transaksi (`asset_transactions.project_id`), dan BAST (melalui
  transaksi). Aturan identik dengan karyawan 01I:
  - ALL_TENANT: semua;
  - SELECTED_PROJECTS: hanya aset/transaksi/BAST yang project-nya ada dalam scope;
  - aset **tanpa project** hanya terlihat oleh ALL_TENANT (fail-closed);
  - UUID di luar scope → **404**;
  - aksi tenant-wide yang belum scope-aware → **403**.
- Penyerahan oleh restricted: aset dalam scope **dan** karyawan dalam scope **dan** project transaksi dalam scope.
- Pengembalian / pemeriksaan / BAST / lampiran: cek ulang scope melalui project transaksi dan aset (pola `_scoped_submission`
  01H).
- Impor oleh restricted: **403** di iterasi awal (sama seperti impor karyawan 01I). Scope-aware impor = DEFER.
- Helper kecil generik (**MODIFY** `data_scope.py`): `with_project_scope(query, scope, column="project_id")` +
  `assert_project_record_visible(scope, record)` agar tidak menyalin logika. Modul `asset` **tidak** ditambahkan ke
  `UNSCOPED_MODULES`.
- Project/lokasi aset **tidak** otomatis mengikuti transfer assignment karyawan (01D). Aset tetap di project saat serah
  sampai dikembalikan. Laporan "aset dipegang karyawan yang sudah pindah project" disediakan sebagai **peringatan**
  (DEFER opsional).

---

## P. Future Exit Clearance (**DEFER**, siapkan kait)

- Helper `outstanding_assets(company_id, employee_id)` = holding ACTIVE (termasuk saldo awal) + transaksi RETURN yang masih
  DRAFT.
- Tahap 2A: tampil di Profil 360 dan export. Opsional: **peringatan** (bukan blok) di `POST /employees/{id}/status-change`
  (`routers/employee_status.py:292`) saat pindah ke kategori INACTIVE.
- Fase Exit Clearance nanti: hard rule "final clearance ditolak bila outstanding > 0", dengan memanggil helper yang sama.

---

## Q. Skema baru minimal (usulan migration `m0012_asset_bast`, aditif + idempoten) — belum dibuat

| Tabel | Tujuan |
|---|---|
| `asset_categories`, `asset_units`, `asset_conditions`, `asset_statuses` | master configurable (engine master generik) |
| `assets` | master aset individual |
| `asset_holdings` | pemegang aktif/riwayat (unique `active_lock`) |
| `asset_transactions`, `asset_transaction_lines` | penyerahan / pengembalian / pemeriksaan / relokasi / saldo awal |
| `asset_events` | histori append-only |
| `asset_bast_documents` | BAST (nomor sistem + manual, PDF, signed copy, snapshot) |
| `document_sequences` | engine penomoran generik |
| `asset_import_batches`, `asset_import_rows` | impor 2 jenis |

Perubahan non-tabel:
- RBAC: modul `asset` "Aset & BAST", resource `asset` (view/create/edit/delete/export/import), `asset_transaction`
  (view/create/approve/export), `asset_bast` (view/create/export), `asset_master` (view/create/edit/delete),
  `asset_config` (config), izin sensitif nilai perolehan;
- `documents.OWNER_TYPES` + aturan scope untuk owner non-employee;
- seed master default per tenant saat modul diaktifkan.

Tidak ada perubahan pada tabel existing (kecuali data konfigurasi/seed). Tidak ada backfill ke data karyawan.

---

## R. Urutan implementasi yang direkomendasikan

| Step | Isi | Output uji |
|---|---|---|
| **2A-2 Foundation** | m0012 (master + assets + events + sequences), RBAC modul `asset`, 4 master via engine generik (+ seed), CRUD Master Asset (kode unik, SN unik, kategori wajib SN), list/detail **scope-aware** + 404, event CREATED/UPDATED, audit, menu "Aset & BAST" + halaman daftar/detail/form | targeted test + scope test |
| **2A-3 Lifecycle** | holdings + transaksi HANDOVER / RETURN / INSPECTION / RELOCATION, hard rules (1 holder, no A→B, READY-only, lock), lampiran transaksi | test balapan, larangan A→B, scope |
| **2A-4 BAST** | `document_sequences` + format configurable, nomor sistem + manual, generate/preview/PDF, VOID, signed copy, pencarian/filter nomor | test unik/immutable/konkurensi |
| **2A-5 Profil 360** | tab Aset + outstanding helper | UI |
| **2A-6 Impor Master Asset** | template → analyze → preview → commit → riwayat | 5 kelas baris |
| **2A-7 Impor Saldo Awal** | OPENING_BALANCE + BAST EXISTING_REFERENCE + BAST Konfirmasi Existing | tanpa histori palsu |
| **2A-8 Export** | 7 export + filter + scope | scope/403 |
| **2A-9** | regression 01B–01I, staging E2E, LOCK | — |

Setiap step berakhir dengan STOP untuk review sesuai pola 01x.

---

## S. Risiko

| # | Risiko | Mitigasi |
|---|---|---|
| 1 | Pola nomor existing (`count_documents`) ditiru → nomor BAST ganda saat bersamaan | Engine `document_sequences` + FOR UPDATE + unique index; jangan meniru kontrak/kandidat |
| 2 | Status configurable merusak lifecycle | `lifecycle_state` sistem otoritatif; status tenant hanya label berkategori (pola 01B) |
| 3 | Dua holder aktif akibat balapan | row-lock aset + unique `active_lock` (dijaga DB) |
| 4 | Histori palsu saat saldo awal | transaksi OPENING_BALANCE bertanggal impor, `start_date_known`, event khusus |
| 5 | Nomor manual lama ganda / format bebas | tidak unik keras; peringatan duplikat; index pencarian |
| 6 | Kebocoran scope melalui dokumen/BAST/lampiran owner non-employee | aturan scope owner_type baru di `documents.py` (saat ini hanya employee yang scope-aware; restricted wajib fail-closed untuk owner lain) |
| 7 | Aset tanpa project tak terlihat oleh restricted | sesuai prinsip fail-closed; laporan "aset tanpa project" untuk ALL_TENANT |
| 8 | Karyawan pindah project (01D) sementara aset tetap di project lama → hilang dari scope PIC project baru | aset tidak ikut otomatis; laporan peringatan; return-handover formal |
| 9 | PDF berubah bila master berubah | snapshot JSON saat generate; regenerasi dilarang setelah SIGNED |
| 10 | Nilai perolehan sensitif | izin terpisah; disembunyikan di export tanpa izin |
| 11 | Impor besar (ribuan aset) | batch + commit per baris; pola 01C sudah teruji |
| 12 | 01H belum merge (PR #17) dan 01I belum di-PR | Phase 2A dibangun di atas branch 01I **setelah** 01H/01I masuk main, atau dari branch 01I lokal. Tentukan saat Step 2 |
| 13 | Scope creep ke bulk inventory / maintenance / depresiasi | DEFER eksplisit (§F) |

---

## T. Keputusan yang perlu direview pengguna sebelum Step 2

1. Satu transaksi boleh berisi **beberapa aset** (satu BAST multi-baris)? *Rekomendasi: ya.*
2. Kode aset: manual, otomatis (sequence + prefix kategori), atau keduanya? *Rekomendasi: keduanya (otomatis bila dikosongkan).*
3. Nomor BAST manual: cukup peringatan duplikat atau wajib unik? *Rekomendasi: peringatan.*
4. Format default nomor sistem: `BAST-AST/{YYYY}/{SEQ:6}` (serah), `BAST-RTN/{YYYY}/{SEQ:6}` (kembali), `BAST-EXS/{YYYY}/{SEQ:6}`
   (existing). Reset tahunan?
5. Pemeriksaan GA: boleh digabung dalam form pengembalian? *Rekomendasi: ya (opsional terpisah).*
6. Approval penyerahan: DEFER? *Rekomendasi: DEFER.*
7. Nilai perolehan: dipakai sekarang atau DEFER?
8. Basis branch Phase 2A: tunggu 01H + 01I merge ke main, atau lanjut di atas branch 01I lokal?

---

STOP — audit selesai. Tidak ada coding, migration, commit, push, PR, merge, atau deploy. Production Changed: **NO**.
