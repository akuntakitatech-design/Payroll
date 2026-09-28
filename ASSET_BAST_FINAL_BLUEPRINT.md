# PHASE 2A — MANAJEMEN ASET (ASSET & BAST CONTROL) · STEP 2: FINAL BLUEPRINT & IMPLEMENTATION PLAN

Revisi 2 (2026-09-28): menu top-level "Manajemen Aset", Profil 360 sebagai contextual view read-only, role GA = preset permission tanpa logic berbasis nama role.

Status: **BLUEPRINT FINAL — BELUM CODING.** Tidak ada migration, tabel, endpoint, UI, commit, push, PR, merge, atau deploy.
Production Changed: **NO** · Dokumen audit: `/app/ASSET_BAST_AUDIT_BLUEPRINT.md` (Step 1, disetujui).
**Prasyarat coding:** 01H (PR #17) **dan** 01I sudah masuk `main`. Phase 2A dibangun di branch baru dari `origin/main` terbaru,
bukan di atas branch 01I lokal.

---

## 0. Keputusan final yang mengikat

| # | Keputusan |
|---|---|
| D1 | Satu transaksi/BAST boleh memuat **beberapa aset**. **BAST = header** dokumen/transaksi, **aset = item**. Setiap item tetap punya lifecycle, kondisi, kelengkapan, dan histori individual. |
| D2 | **Pengembalian boleh parsial.** Hanya aset yang dikembalikan yang masuk BAST Pengembalian baru. Aset lain dari BAST Penyerahan yang sama tetap dipegang. |
| D3 | Kode Asset **manual atau otomatis**. Jika kosong → generate otomatis. Kode existing tidak pernah ditimpa. **Unik per company.** |
| D4 | Nomor BAST Manual/Referensi **tidak wajib unik**. Duplikat hanya memunculkan **warning**. |
| D5 | Nomor BAST Sistem **wajib unik dan concurrency-safe**. |
| D6 | Format default: `BAST-AST/{YYYY}/{SEQ:6}` · `BAST-RTN/{YYYY}/{SEQ:6}` · `BAST-EXS/{YYYY}/{SEQ:6}`. **Reset tiap tahun**, counter terpisah per company dan per jenis BAST, format **configurable**. |
| D7 | Pemeriksaan GA adalah **bagian workflow Pengembalian**. Status **Menunggu Pemeriksaan** didukung bila pemeriksaan tidak dilakukan langsung. |
| D8 | Approval Penyerahan **DEFER**. |
| D9 | Nilai Perolehan dan Tanggal Perolehan tersedia sekarang sebagai **field opsional**. Depresiasi/akuntansi **DEFER**. |
| D10 | 1 Kode Asset = 1 unit fisik. Satuan hanya label. Maks 1 pemegang aktif. Tidak ada perpindahan langsung A→B. |
| D11 | Mengikuti 01I: ALL_TENANT / SELECTED_PROJECTS, UUID di luar scope → 404, aksi tenant-wide belum scope-aware → 403, fail-closed. |
| D12 | **"Manajemen Aset" = menu top-level tersendiri**, bukan submenu Data Karyawan/HR. Submenu: Dashboard · Daftar Aset · Penyerahan Aset · Pengembalian & Pemeriksaan · Dokumen BAST · Impor Aset · Laporan & Export · Pengaturan. |
| D13 | **Profil 360 → tab Aset** adalah *contextual employee view* (read-only) dari **data modul Manajemen Aset yang sama**. Bukan database kedua dan bukan modul kedua. **Seluruh transaksi tetap dilakukan di Manajemen Aset.** |
| D14 | Role default baru **GA Admin** dan **GA Staff** disetujui sebagai *preset* permission. **Tidak ada business logic berdasarkan nama role.** Semua cek memakai permission/RBAC existing (`require_permission(resource, action)`), sehingga role lain (mis. **HRGA Admin**) dapat diberi hak yang sama lewat matriks izin. |

---

## 1. Menu & submenu

Modul baru **`asset` — "Manajemen Aset"** (non-core; aktif lewat **Aktivasi Modul**).

Tampil sebagai **grup menu top-level tersendiri** di sidebar (`lib/nav.js`), sejajar dengan Kepegawaian dan Payroll & Pajak.
Grup ini **tidak** ditaruh di bawah Data Karyawan/HR. Layout `pages/asset/AssetModuleLayout.jsx` (pola
`LeaveOvertimeModuleLayout`). Prefix route: `/modules/asset`. Grup hanya tampil bila modul aktif dan user punya minimal satu
izin `asset*`.

Submenu **Manajemen Aset** (urutan final):

| Submenu | Route | Isi | Izin minimum |
|---|---|---|---|
| Dashboard | `/modules/asset` | KPI + daftar tindak lanjut (§13) | `asset.view` |
| Daftar Aset | `/modules/asset/assets` | list/filter/cari, detail aset (tab Info, Pemegang, Histori, BAST, Lampiran), tambah/ubah | `asset.view` |
| Penyerahan Aset | `/modules/asset/handovers` | daftar BAST Penyerahan + form baru | `asset_handover.view` |
| Pengembalian & Pemeriksaan | `/modules/asset/returns` | tab **Pengembalian**, tab **Menunggu Pemeriksaan** (antrean GA) | `asset_return.view` |
| Dokumen BAST | `/modules/asset/bast` | register semua BAST (AST/RTN/EXS), cari nomor sistem/manual, detail, PDF, signed copy | `asset_bast.view` |
| Impor Aset | `/modules/asset/imports` | wizard **Master Asset** dan **Saldo Awal di Karyawan** + riwayat impor | `asset.import` |
| Laporan & Export | `/modules/asset/reports` | 7 export + filter | `asset.export` |
| Pengaturan Aset | `/modules/asset/settings` | sub-tab: Kategori · Satuan · Kondisi · Status · Penomoran · Teks BAST | `asset_master.view` / `asset_config.config` |

Integrasi di luar modul (bukan menu kedua):
- **Data Karyawan → Profil 360 → tab "Aset (n)"** (§12): tampilan kontekstual read-only dari data Manajemen Aset. Tautan dari
  tab membuka halaman terkait di Manajemen Aset.
- (DEFER opsional) ESS "Aset Saya": read-only aset dan BAST milik sendiri.

---

## 2. Konfigurasi master (Pengaturan Aset)

Memakai **engine master generik** (`masters.py` + `routers/master.py`): list, create, edit, aktif/nonaktif, dan hapus dengan cek
referensi. Seed default per tenant **idempoten** saat modul pertama kali diaktifkan. Tenant bebas menambah, mengubah label,
atau menonaktifkan.

| Master | resource_path | Field form | Seed default |
|---|---|---|---|
| Kategori | `asset-categories` | Kode*, Nama*, Prefix Kode Aset (opsional, mis. `LPT`), Wajib Serial Number (switch), Satuan Default, Deskripsi | Laptop (LPT, SN wajib), Handphone (HP, SN wajib), Kendaraan (KDR, SN wajib), Kamera (KMR, SN wajib), Alat Kerja (ALT), Furnitur (FRN), Lainnya (LN) |
| Satuan | `asset-units` | Kode*, Nama*, Deskripsi | Unit, Pcs, Set, Pasang, Buah, Paket (**tidak hardcode**; hanya seed) |
| Kondisi | `asset-conditions` | Kode*, Nama*, Dapat Dipakai (switch), Tingkat (0–9), Deskripsi | Baik (dapat dipakai), Baik – Lecet Ringan (dapat dipakai), Rusak Ringan, Rusak Berat, Hilang |
| Status | `asset-statuses` | Kode*, Nama*, **Kategori Sistem*** (pilihan tetap), Default untuk kategori ini (switch), Deskripsi | 1 status default per kategori sistem (§7) |

Aturan:
- Kategori sistem status **tidak bisa diubah** setelah status dipakai aset.
- Tiap kategori sistem wajib punya tepat 1 status default aktif (validasi backend).
- Kondisi "Dapat Dipakai = tidak" tidak boleh dipilih sebagai kondisi awal saat Penyerahan.

---

## 3. Form Master Asset

**Daftar Aset.** Kolom: Kode, Nama, Kategori, Merk/Tipe, SN, Project, Lokasi, Kondisi, Status (badge warna per kategori
sistem), Pemegang saat ini, Nomor BAST terakhir.
Filter: Project, Lokasi, Kategori, Satuan, Status, Kondisi, Pemegang, "Tanpa project". Cari: kode, nama, SN, merk, nama/NIK
pemegang. Pagination server-side. List **tidak** menampilkan nilai perolehan.

**Form Tambah/Ubah Aset** (Dialog/Sheet, shadcn):

| Field | Wajib | Validasi |
|---|---|---|
| Kode Asset | tidak | kosong → otomatis (§8.3); diisi → unik per company (case-insensitive, trim); **tidak bisa diubah** setelah aset punya transaksi/histori selain CREATED |
| Nama Asset | ya | ≤ 255 |
| Kategori | ya | master aktif |
| Satuan | ya | master aktif; default dari kategori |
| Merk | tidak | |
| Tipe / Model | tidak | |
| Serial Number | kondisional | wajib bila kategori "Wajib SN"; unik per company bila diisi (normalisasi upper + hapus spasi) |
| Tanggal Perolehan | tidak | tanggal valid ≤ hari ini |
| Tahun Perolehan | tidak | 4 digit; otomatis dari tanggal bila tanggal diisi |
| Nilai Perolehan | tidak | desimal ≥ 0; tampil/edit hanya dengan izin `asset_value` |
| Project | tidak* | master aktif; **harus dalam scope** caller. *Restricted wajib memilih project dalam scope-nya |
| Lokasi Kerja | tidak | master aktif |
| Kondisi | ya | master aktif; default "Baik" |
| Status | ya (create) | hanya status berkategori READY / MAINTENANCE / DAMAGED / LOST / DISPOSED. **IN_USE dan PENDING_INSPECTION tidak bisa dipilih manual** |
| Keterangan | tidak | |

Aturan edit:
- Saat aset IN_USE atau PENDING_INSPECTION: Project, Lokasi, Kondisi, dan Status **terkunci**. Hanya berubah lewat transaksi.
- Perubahan status manual antar READY ↔ MAINTENANCE ↔ DAMAGED → LOST/DISPOSED lewat aksi **"Ubah Status"** dengan alasan
  wajib, dicatat sebagai event.
- DISPOSED bersifat terminal (hanya bisa dibatalkan oleh `asset.delete` dengan alasan).
- Hapus aset hanya bila belum pernah punya transaksi. Selain itu gunakan DISPOSED.

**Detail Aset** (tab):
1. Info;
2. Pemegang (aktif + riwayat holding);
3. Histori (timeline event append-only);
4. BAST (semua BAST yang memuat aset ini, dengan nomor sistem + manual);
5. Lampiran (dokumen owner `asset`).

Aksi: Ubah, Ubah Status, Relokasi (hanya READY), Serahkan (jika READY → buka form Penyerahan dengan aset terpilih).

---

## 4. Form Penyerahan (BAST Penyerahan — `bast_type = HANDOVER`)

**Header**

| Field | Wajib | Aturan |
|---|---|---|
| Karyawan penerima | ya | kategori status ACTIVE/STANDBY (bukan INACTIVE); **dalam scope** |
| Project | ya | default = project assignment ACTIVE karyawan (01D); dalam scope |
| Lokasi Kerja | tidak | default = lokasi assignment / lokasi project |
| Tanggal Serah | ya | ≤ hari ini + 0; tidak sebelum tanggal perolehan aset |
| PIC GA (Pihak Pertama) | ya | user tenant aktif (default: user login); nama & jabatan disnapshot |
| Nomor BAST Manual/Referensi | tidak | bebas; duplikat → **warning** non-blocking ("Nomor ini sudah dipakai di BAST …") |
| Catatan | tidak | |
| Lampiran | tidak | foto serah terima / dokumen lain (owner `asset_bast`) |

**Item (1..n)**, dipilih dari aset **READY** dalam scope (picker dengan cari kode/SN/nama, filter kategori/project):

| Field per item | Wajib | Aturan |
|---|---|---|
| Aset | ya | READY, tidak duplikat dalam BAST yang sama |
| Kondisi Awal | ya | kondisi "Dapat Dipakai"; default = kondisi terakhir aset |
| Kelengkapan | tidak | checklist item bebas (mis. Charger ✔, Tas ✔, Mouse ✘) + teks tambahan |
| Catatan item | tidak | |

**Alur state**
- **Simpan Draft** → `DRAFT`: aset **belum** dikunci, tanpa nomor sistem. Draft dapat diubah atau dihapus.
- **Terbitkan** → `ISSUED`, dalam satu transaksi DB:
  1. lock semua aset (FOR UPDATE) dan validasi ulang READY + scope;
  2. alokasikan **nomor sistem** (§8);
  3. buat `asset_holdings` ACTIVE per item;
  4. aset → IN_USE, project/lokasi mengikuti header, kondisi = kondisi awal;
  5. event HANDOVER per aset;
  6. audit;
  7. snapshot BAST.

  Gagal satu item → **seluruh BAST gagal** (atomik; pesan menyebut aset bermasalah).
- Setelah ISSUED: **Pratinjau** → **Unduh PDF** → cetak dan tanda tangan → **Unggah Salinan Bertanda Tangan** → `SIGNED`.
- **Batalkan (VOID)** hanya bila ISSUED, belum SIGNED, dan **belum ada item yang dikembalikan**. Alasan wajib. Holding
  dibatalkan (status `CANCELLED`, bukan dihapus), aset kembali READY, dan nomor sistem **tidak dipakai ulang**. Event
  BAST_VOID.

---

## 5. Form Pengembalian + Pemeriksaan (BAST Pengembalian — `bast_type = RETURN`)

**Langkah 1 — Pilih karyawan.** Sistem menampilkan semua holding ACTIVE karyawan (lintas BAST Penyerahan / Saldo Awal)
dalam scope. User mencentang aset yang dikembalikan → **parsial didukung**.

**Header**

| Field | Wajib | Aturan |
|---|---|---|
| Karyawan | ya | dalam scope |
| Tanggal Kembali | ya | ≥ tanggal mulai holding tiap item; ≤ hari ini |
| Diterima oleh (PIC GA) | ya | user tenant aktif |
| Project / Lokasi pengembalian | ya / tidak | default project holding; dalam scope |
| Nomor BAST Manual/Referensi | tidak | duplikat → warning |
| Catatan | tidak | |
| Lampiran / Foto | tidak | owner `asset_bast` |

**Item (aset yang dikembalikan)**

| Field | Wajib |
|---|---|
| Kondisi saat kembali | ya |
| Kelengkapan saat kembali | tidak (checklist dibandingkan dengan kelengkapan saat serah; item kurang disorot) |
| Kerusakan / catatan | tidak (wajib bila kondisi tidak "Dapat Dipakai" atau kelengkapan kurang) |
| **Periksa sekarang** (switch per item, default ON) | — |
| Hasil pemeriksaan (jika diperiksa sekarang) | ya: **Siap Pakai (READY) / Maintenance / Rusak (DAMAGED) / Hilang (LOST) / Disposed** |
| Kondisi final pemeriksaan | ya bila diperiksa |
| Catatan pemeriksaan | tidak |

**Terbitkan** → `ISSUED`, dalam satu transaksi DB:
1. lock aset + holding;
2. nomor sistem RTN;
3. holding → `ENDED` (end_date, kondisi kembali, `return_bast_id`);
4. untuk item yang **diperiksa sekarang**: aset → state hasil pemeriksaan, event RETURN + INSPECTION;
5. untuk item yang **tidak diperiksa**: aset → **PENDING_INSPECTION** ("Menunggu Pemeriksaan"), event RETURN;
6. audit;
7. snapshot.

`inspection_state` header:
- `COMPLETED` bila semua item sudah diperiksa;
- `PENDING` bila masih ada item yang menunggu.

**Tab "Menunggu Pemeriksaan"**: antrean item dengan inspection_status PENDING (aging dalam hari). Aksi **Periksa** (per item
atau massal): hasil + kondisi final + catatan + foto (lampiran BAST). Header otomatis menjadi COMPLETED setelah item terakhir
diperiksa.
- Pemeriksaan **tidak** membuat BAST baru dan **tidak** mengubah nomor.
- Jika BAST belum SIGNED, PDF dapat diregenerasi agar memuat hasil pemeriksaan. Jika sudah SIGNED, hasil pemeriksaan hanya
  tercatat di sistem.

Aturan:
- Aset PENDING_INSPECTION / MAINTENANCE / DAMAGED / LOST tidak bisa diserahkan.
- **Tidak ada A→B langsung**: karyawan B hanya bisa menerima setelah aset READY.

---

## 6. Form / Detail BAST (Dokumen BAST)

**Register BAST.** Kolom: Nomor Sistem, Nomor Manual, Jenis (Penyerahan / Pengembalian / Existing), Tanggal, Karyawan
(nama + NIK), Project, Jumlah aset, Status Dokumen (Draft / Terbit / Ditandatangani / Batal), Pemeriksaan (untuk RTN:
Selesai / Menunggu n), Signed copy (ada/tidak).
Filter: jenis, status, project, lokasi, karyawan, periode, "belum ditandatangani", nomor manual duplikat. Cari: nomor sistem
**dan** nomor manual (dua-duanya diindeks).

**Detail BAST**
- Header: nomor sistem (read-only, tombol salin), nomor manual (edit dengan izin `asset_bast.edit`, perubahan dicatat
  before/after), pihak, tanggal, catatan.
- Item: aset, kondisi, kelengkapan, catatan, hasil pemeriksaan (RTN).
- Lampiran dan riwayat audit.
- Aksi: Pratinjau · Unduh PDF · Unggah Salinan Bertanda Tangan · Ganti Salinan (versi baru, lama tetap tersimpan) · Batalkan
  (sesuai aturan §4) · Regenerasi PDF (hanya sebelum SIGNED).

**Isi PDF** (reportlab, pola `core/pdf.py`):
- kop (logo + nama + alamat tenant);
- judul "BERITA ACARA SERAH TERIMA ASET" / "BERITA ACARA PENGEMBALIAN ASET" / "BERITA ACARA KONFIRMASI ASET EXISTING";
- Nomor (sistem) + "Ref. Manual: …" bila ada;
- tanggal;
- Pihak Pertama (PIC GA: nama, jabatan) dan Pihak Kedua (karyawan: nama, NIK karyawan, jabatan, project, lokasi);
- teks pembuka (configurable);
- tabel item: No, Kode, Nama, Merk/Tipe, SN, Satuan, Kondisi, Kelengkapan, Catatan; untuk RTN ditambah kolom Hasil Periksa;
- teks penutup (configurable);
- kolom tanda tangan kedua pihak (+ Mengetahui, opsional).

PDF dibangun dari **snapshot** saat diterbitkan, sehingga perubahan master tidak mengubah dokumen lama.

---

## 7. Lifecycle & status

**Kategori sistem (`lifecycle_state`)** dikunci di kode dan menjadi sumber otoritatif:

| State | Label default | Masuk dari | Keluar ke |
|---|---|---|---|
| `READY` | Siap Pakai | create, inspeksi READY, selesai maintenance, void BAST penyerahan | IN_USE (penyerahan), MAINTENANCE, DAMAGED, LOST, DISPOSED (ubah status) |
| `IN_USE` | Dipakai | penyerahan, saldo awal (impor) | PENDING_INSPECTION / hasil inspeksi (pengembalian) |
| `PENDING_INSPECTION` | Menunggu Pemeriksaan | pengembalian tanpa periksa langsung | READY, MAINTENANCE, DAMAGED, LOST, DISPOSED (pemeriksaan) |
| `MAINTENANCE` | Perbaikan | inspeksi / ubah status | READY, DAMAGED, DISPOSED |
| `DAMAGED` | Rusak | inspeksi / ubah status | MAINTENANCE, DISPOSED |
| `LOST` | Hilang | inspeksi / ubah status | READY (ditemukan, alasan wajib), DISPOSED |
| `DISPOSED` | Dihapuskan | inspeksi / ubah status | — (terminal) |

- Status tenant (`asset_statuses`) = label + warna per kategori sistem. Transisi hanya lewat engine (`core/asset_lifecycle.py`),
  dan transisi ilegal → 409.
- **Invariant (dijaga DB + engine):** `lifecycle_state = IN_USE` ⇔ ada tepat 1 holding ACTIVE. Tidak pernah 2 holding ACTIVE
  (unique `active_lock`).
- **Relokasi** (READY saja): ubah project/lokasi tanpa pemegang. Event RELOCATION, tanpa BAST.

---

## 8. Numbering

### 8.1 Engine generik `core/doc_sequence.py`
Tabel `document_sequence_configs` dan `document_sequence_counters` (§15). Dapat dipakai modul lain di masa depan
(kontrak/kandidat = DEFER).

- **Token format:** `{YYYY}` `{YY}` `{MM}` `{ROMAN_MM}` `{COMPANY}` (kode tenant) `{CAT}` (prefix kategori, khusus kode aset)
  `{SEQ:n}` (n = 3–9 digit). Teks lain literal.
- **Validasi format:**
  - wajib memuat tepat satu `{SEQ:n}`;
  - bila `reset_policy = YEARLY`, wajib memuat `{YYYY}` atau `{YY}` (mencegah tabrakan antar tahun);
  - panjang hasil ≤ 64;
  - pratinjau contoh langsung di UI.
- **Alokasi (concurrency-safe)** di dalam transaksi DB yang sama dengan penerbitan BAST:
  1. `period_key` = tahun dari **tanggal BAST** (YEARLY) atau `ALL`;
  2. `SELECT … FOR UPDATE` baris counter `(company_id, sequence_key, period_key)`; bila belum ada → INSERT (unique; bila
     konflik karena balapan → ulangi SELECT FOR UPDATE);
  3. nilai = `next_value`, lalu `next_value += 1`;
  4. render format;
  5. jika nomor hasil sudah ada (mis. format pernah diganti) → naikkan dan ulangi (maks 50);
  6. unique index `(company_id, system_number)` pada `asset_bast` menjadi jaring pengaman terakhir.
- **Counter tidak pernah mundur.** VOID tidak mengembalikan nomor. Gap dicatat, dan nomor tidak dipakai ulang.
- **Perubahan format** berlaku untuk nomor berikutnya. Nomor yang sudah terbit tidak berubah (immutable, tidak ada endpoint
  edit).

### 8.2 Sequence default (seed per tenant)

| sequence_key | Format default | Reset |
|---|---|---|
| `BAST_HANDOVER` | `BAST-AST/{YYYY}/{SEQ:6}` | YEARLY |
| `BAST_RETURN` | `BAST-RTN/{YYYY}/{SEQ:6}` | YEARLY |
| `BAST_EXISTING` | `BAST-EXS/{YYYY}/{SEQ:6}` | YEARLY |
| `ASSET_CODE` | `{CAT}-{SEQ:5}` (tanpa prefix kategori → `AST-{SEQ:5}`) | NEVER; counter per `{CAT}` (period_key = prefix kategori) |

Semua dapat diubah di **Pengaturan Aset → Penomoran** (izin `asset_config.config`, diaudit).

### 8.3 Kode Asset otomatis
Kode kosong saat create atau impor → alokasi `ASSET_CODE` dalam transaksi create. Kode hasil yang bentrok dengan kode manual
existing → dilewati ke nomor berikutnya. Kode manual tidak pernah diubah sistem.

### 8.4 Nomor manual
Disimpan apa adanya (`manual_number`) + kolom normalisasi (`manual_number_norm`: upper, trim, spasi tunggal) untuk
pencarian dan deteksi duplikat. Duplikat → warning di form, impor (kolom "Peringatan"), dan filter register. Tidak pernah
blocking.

---

## 9. Import Master Asset

Wizard pola Core HR 01C: **Unduh Template → Upload → Analisis (read-only) → Pratinjau → Validasi → Commit (file hash wajib
sama) → Riwayat Impor.**

**Template xlsx**
- Sheet `Petunjuk`;
- Sheet `Data` berisi kolom: Kode Asset, Nama Asset*, Kategori*, Satuan*, Merk, Tipe/Model, Serial Number, Tanggal
  Perolehan, Tahun Perolehan, Nilai Perolehan, Kode Project, Kode Lokasi Kerja, Kondisi*, Status*, Keterangan;
- Sheet `Referensi`: daftar kode/nama master aktif tenant.

| Kelas | Kriteria |
|---|---|
| **NEW** | kode kosong (→ otomatis saat commit) atau kode belum ada |
| **UPDATE** | kode ada dan ≥1 field berbeda. Pratinjau menampilkan per field "lama → baru". Kolom kosong di file = **tidak mengubah** (bukan menghapus) |
| **UNCHANGED** | identik |
| **CONFLICT** | kode duplikat dalam file; SN duplikat (file / aset lain); mengubah project/lokasi/kondisi/status aset IN_USE atau PENDING_INSPECTION; status berkategori IN_USE/PENDING_INSPECTION; perubahan status melanggar lifecycle (mis. DISPOSED → READY); nilai perolehan diisi tanpa izin `asset_value` |
| **ERROR** | kolom wajib kosong; kategori/satuan/kondisi/status/project/lokasi tidak ditemukan (dicocokkan by kode, lalu nama persis case-insensitive); SN kosong untuk kategori wajib SN; format tanggal/angka salah; project di luar company |

- Commit hanya NEW + UPDATE, **per baris transaksional**. CONFLICT/ERROR tidak pernah di-commit (no silent overwrite).
- Event IMPORTED/UPDATED_MASTER per aset. Batch dan baris tersimpan di riwayat.
- Impor master **tidak pernah** membuat holding.

---

## 10. Import Saldo Awal Asset di Karyawan

Wizard sama (jenis `OPENING_HOLDING`).

**Template** kolom: Kode Asset*, Nomor Induk Karyawan*, Nama Karyawan* (validasi), Tanggal Mulai Pegang, Kode Project*,
Kode Lokasi Kerja, Kondisi*, Kelengkapan, Nomor BAST Manual/Existing, Catatan.

| Kelas | Kriteria |
|---|---|
| **NEW** | aset READY tanpa holder, karyawan valid |
| **UNCHANGED** | aset sudah dipegang karyawan yang **sama** dari saldo awal sebelumnya (idempoten, re-upload aman) |
| **CONFLICT** | aset sudah punya active holder (karyawan lain / BAST sistem); aset bukan READY; nama tidak cocok dengan NIK (normalisasi); karyawan INACTIVE; aset muncul >1 kali di file; nomor BAST manual dipakai untuk karyawan berbeda (warning, dinaikkan ke CONFLICT bila sekaligus beda project; dapat dikonfirmasi) |
| **ERROR** | kode aset / NIK / project / lokasi / kondisi tidak ditemukan; tanggal salah atau di masa depan; kolom wajib kosong |

**UPDATE tidak didukung** untuk saldo awal. Koreksi dilakukan lewat Pengembalian lalu impor ulang/penyerahan, agar histori
jujur.

**Commit per baris** (transaksional):
1. `asset_holdings` ACTIVE, `source = OPENING_BALANCE`, `start_date` = tanggal mulai bila diketahui, `start_date_known =
   false` bila kosong;
2. aset → IN_USE + project/lokasi/kondisi dari file;
3. event **OPENING_BALANCE** ("Saldo Awal — Penempatan Existing, impor batch …") bertanggal **saat impor**. **Tidak** dibuat
   event HANDOVER atau tanggal serah fiktif;
4. **Jika Nomor BAST Manual diisi**: baris dikelompokkan per (karyawan + nomor manual) → **satu BAST EXS per kelompok**
   (`bast_type = EXISTING`, `existing_mode = REFERENCE`, `manual_number` disimpan, **nomor sistem EXS dialokasikan**, tanpa
   PDF sistem; scan BAST lama dapat diunggah sebagai signed copy);
5. **Jika kosong**: holding tanpa BAST. Dapat dibuat kemudian **BAST Konfirmasi Existing** (`existing_mode = CONFIRMATION`)
   di **Manajemen Aset → Dokumen BAST** (tautan pintas tersedia dari Profil 360): pilih karyawan → pilih holding saldo awal
   tanpa BAST → terbitkan (nomor EXS + PDF) → tanda tangan → unggah. Tersedia juga aksi massal per project.

---

## 11. Export

Format xlsx (openpyxl). Semua export **scope-aware**: query dibatasi `allowed_project_ids`. Restricted hanya mendapat data
project dalam scope-nya; aset/BAST tanpa project hanya untuk ALL_TENANT. Nilai perolehan hanya dengan izin `asset_value`.

| Export | Baris | Kolom utama |
|---|---|---|
| Master Asset | aset | semua field master, lifecycle/status, kondisi, pemegang saat ini, BAST terakhir |
| Asset Dipakai | holding ACTIVE | aset, karyawan, NIK, project, lokasi, mulai pegang (+ "Saldo Awal / tanggal tidak diketahui"), kondisi keluar, kelengkapan, BAST sistem/manual |
| Asset per Karyawan | holding ACTIVE + riwayat (opsional) | dikelompokkan per karyawan |
| Asset per Project | aset | dikelompokkan per project |
| Asset per Lokasi | aset | dikelompokkan per lokasi |
| Histori Asset | asset_events | waktu, aset, event, dari→ke state, karyawan, project, lokasi, kondisi, BAST sistem/manual, aktor, catatan |
| Daftar BAST | header + item | nomor sistem, nomor manual (+ flag duplikat), jenis, tanggal, karyawan, project, aset, status dokumen, pemeriksaan, signed copy |

Filter umum: Project, Lokasi, Kategori, Satuan, Status, Kondisi, Karyawan, Periode (tanggal event/BAST), Jenis BAST.

---

## 12. Profile 360 — Data Karyawan → Profil 360 → Aset (contextual employee view)

**Prinsip**
- Tab "Aset (n)" di `EmployeeDetailPage.jsx` adalah **tampilan kontekstual read-only**. **Tidak ada tabel, engine, atau
  modul kedua.** Semua data dibaca dari tabel Manajemen Aset yang sama (`assets`, `asset_holdings`, `asset_bast`,
  `asset_bast_items`, `asset_events`) melalui service yang sama (`core/asset_*`).
- **Tidak ada transaksi di Profil 360.** Penyerahan, pengembalian, pemeriksaan, pembuatan BAST, unggah signed copy, dan
  nomor manual hanya dilakukan di Manajemen Aset. Tombol pintas di tab (bila berizin) hanya **navigasi** ke form Manajemen
  Aset dengan karyawan terisi (mis. `/modules/asset/handovers/new?employee_id=…`).
- Endpoint read-only: `GET /api/employees/{id}/assets` (ringkasan + holding aktif + riwayat) dan
  `GET /api/employees/{id}/asset-basts`. Guard: `assert_employee_visible` (01I → 404) + izin `asset.view` + modul `asset` aktif.
  Tab disembunyikan bila salah satu tidak terpenuhi.
- Dimuat **lazy** saat tab dibuka (tidak memperlambat loader profil). Badge jumlah dari endpoint ringkasan ringan.

**Isi minimal tab**

| Bagian | Kolom / isi |
|---|---|
| Ringkasan | **Jumlah aset outstanding** (holding ACTIVE + item pengembalian yang masih Menunggu Pemeriksaan ditandai terpisah), jumlah BAST belum ditandatangani |
| **Aset yang saat ini dipegang** | Kode + Nama (tautan ke Detail Aset), Kategori, SN, **Project / Lokasi**, **Tanggal Penyerahan** (atau "Saldo Awal — tanggal tidak diketahui"), **Kondisi** saat serah, Kelengkapan, **Nomor BAST Sistem / Manual** (tautan ke Detail BAST) |
| **Histori Penyerahan** | Tanggal, Nomor BAST Sistem / Manual, jumlah aset, project, PIC GA, status dokumen (Terbit / Ditandatangani / Batal), tautan Detail BAST |
| **Histori Pengembalian** | Tanggal kembali, Nomor BAST RTN Sistem / Manual, aset yang dikembalikan, kondisi kembali, **Status Pemeriksaan** (Selesai / Menunggu Pemeriksaan n item + hasil per item), tautan Detail BAST |
| Saldo Awal / BAST Existing | holding saldo awal, dengan atau tanpa BAST EXS (nomor manual lama ditampilkan) |

Semua tautan mengarah ke halaman **Manajemen Aset** (Detail Aset `/modules/asset/assets/{id}`, Detail BAST
`/modules/asset/bast/{id}`).

**Scope 01I di tab**
- Karyawan harus visible, dan item aset/BAST tetap difilter scope project.
- Item di project di luar scope caller ditampilkan sebagai "Di luar cakupan akses" tanpa kode/nama/nomor (pola atasan 01I),
  tetapi tetap dihitung dalam jumlah outstanding agar HR tidak salah menyimpulkan "tidak ada aset".

Ringkasan profil juga menampilkan badge **"Aset outstanding: n"** sebagai fondasi Exit Clearance
(helper `outstanding_assets(company_id, employee_id)` yang sama dipakai dashboard dan fase Exit Clearance).

---

## 13. Dashboard / report source

Semua angka dari query agregat scope-aware (tanpa tabel ringkasan; indeks mendukung).

| Widget | Sumber |
|---|---|
| Total aset per lifecycle state | `assets` GROUP BY lifecycle_state |
| Aset per kategori / per project | `assets` GROUP BY category_id / project_id |
| Sedang dipakai | holding ACTIVE count |
| **Menunggu Pemeriksaan** (+ aging > 3 / 7 hari) | `asset_bast_items` inspection_status PENDING |
| BAST belum ditandatangani | `asset_bast` doc_state ISSUED |
| Saldo awal tanpa BAST | holding OPENING_BALANCE tanpa bast EXS |
| **Aset dipegang karyawan INACTIVE** (risiko exit) | holding ACTIVE JOIN status karyawan kategori INACTIVE |
| Aset dipegang karyawan yang project assignment-nya berbeda | holding.project_id ≠ assignment ACTIVE project (peringatan) |
| Aset tanpa project | `assets.project_id IS NULL` (ALL_TENANT saja) |
| Aktivitas terbaru | `asset_events` ORDER BY event_at DESC |

---

## 14. RBAC + 01I scope

### 14.1 Resource (tambahan di `core/rbac.py`, modul `asset`)

| Resource | Aksi | Arti |
|---|---|---|
| `asset` | view, create, edit, delete, import, export | master aset, ubah status, relokasi, impor, export |
| `asset_value` | view, edit | nilai perolehan (sensitif) |
| `asset_master` | view, create, edit, delete | kategori/satuan/kondisi/status |
| `asset_handover` | view, create, delete | BAST penyerahan (buat/terbitkan, void) |
| `asset_return` | view, create, verify | pengembalian, **verify = pemeriksaan GA** |
| `asset_bast` | view, edit, export, manage | register; edit nomor manual & signed copy; manage = void/regenerasi |
| `asset_config` | config | format penomoran, teks BAST |

### 14.2 Role default = preset permission (bukan logic)

**Prinsip:**
- Seluruh otorisasi aset memakai `require_permission(resource, action)` existing (dan `ctx.has_permission` di handler).
- **Tidak ada `if role == "ga_admin"`** atau pengecekan nama role di backend maupun frontend (menu dan tombol memakai
  `can(resource, action)`).
- Role GA Admin dan GA Staff hanya **preset baris `role_permissions`** yang di-seed. Tenant dapat:
  - mengubah hak kedua role itu;
  - memberi hak yang sama ke role lain (mis. membuat/mengubah **HRGA Admin** di matriks izin);
  - atau menambahkan izin aset ke role existing (hr_admin, dll.).
- Pemilihan PIC GA / pemeriksa di form **tidak** dibatasi nama role. Kandidat PIC = user aktif tenant yang punya izin
  `asset_handover.create` (untuk penyerahan) atau `asset_return.verify` (untuk pemeriksaan).

| Role (preset, dapat diubah tenant) | Hak default |
|---|---|
| super_admin / tenant_admin / company_owner | semua (mengikuti perilaku full-access existing) |
| **GA Admin** (`ga_admin`, role sistem baru) | semua resource aset, termasuk `asset_value`, `asset_master` CRUD, `asset.import/export`, `asset_bast.manage`, `asset_config.config` |
| **GA Staff** (`ga_staff`, role sistem baru) | asset view/create/edit; asset_handover view/create; asset_return view/create/verify; asset_bast view/edit; asset_master view; asset export |
| hr_admin / hr_manager | asset view, asset_bast view (Profil 360 & exit); tanpa transaksi (dapat ditambah tenant) |
| finance | asset view, asset_value view, asset export |
| manager / supervisor / employee | tidak ada (ESS "Aset Saya" = DEFER) |
| role kustom tenant (mis. **HRGA Admin**) | tidak ada default; diberi hak lewat matriks izin, sehingga berperilaku identik dengan GA Admin bila izinnya sama |

Seed role/permission aditif dan idempoten: role existing tidak diubah selain penambahan hak lihat aset di atas. Kalau tenant
sudah punya role bernama sama, seed tidak menimpa izin yang sudah diedit tenant.

### 14.3 Enforcement 01I (dibangun scope-aware sejak awal; modul `asset` **tidak** masuk `UNSCOPED_MODULES`)

| Jalur | Aturan restricted (SELECTED_PROJECTS) |
|---|---|
| List aset / BAST / holding / event | SQL `project_id IN allowed` (aset: `assets.project_id`; BAST: `asset_bast.project_id`; holding: `asset_holdings.project_id`). Tanpa project → tidak terlihat |
| Detail UUID aset / BAST / holding | di luar scope → **404** generik |
| Create / edit aset | project wajib dalam scope; tidak boleh memindah aset ke project di luar scope |
| Penyerahan | aset ∈ scope **dan** karyawan ∈ scope (01I `employee_in_scope`) **dan** project header ∈ scope |
| Pengembalian / pemeriksaan | holding & BAST asal ∈ scope; karyawan ∈ scope. Karyawan di luar scope tetapi aset ∈ scope → **403** (tidak menebak), didokumentasikan |
| BAST PDF / signed copy / lampiran | cek ulang scope header (pola `_scoped_submission` 01H); dokumen owner `asset`/`asset_bast` wajib lewat checker scope aset di `documents.py` |
| Export | scope-aware (filter SQL) |
| Impor (kedua jenis) | **403** di rilis 2A (`full_scope_dependency`), konsisten 01I; scope-aware impor = DEFER |
| Dashboard | agregat scope-aware |
| Profil 360 tab Aset | employee harus visible (404); item aset tetap difilter scope (aset di project di luar scope disamarkan "Di luar cakupan akses", pola atasan 01I) |
| Pengaturan (master, penomoran) | konfigurasi company-level → RBAC saja (seperti Approval Workflow di 01I) |

Helper generik baru di `data_scope.py`: `with_project_scope(query, scope, column)` dan
`assert_project_record_visible(scope, record, column)`. Tidak mengubah perilaku 01I existing.

---

## 15. Schema final `m0012_asset_bast` (aditif, idempoten, ledger; dideklarasikan juga di `core/db.py`)

Semua tabel memakai kolom MASTER standar: `id` UUID, `company_id`, `status` (record active/inactive), `created_at`,
`updated_at`, `created_by`, `updated_by`. Tidak ada perubahan pada tabel existing selain data seed (roles, permissions,
masters) dan pendaftaran owner_type dokumen di kode.

### 15.1 Master
| Tabel | Kolom khusus | Index |
|---|---|---|
| `asset_categories` | code s64, name s, code_prefix s32, requires_serial_number b, default_unit_id fk, description t, sort_order i | uq(company_id, code) |
| `asset_units` | code, name, description, sort_order | uq(company_id, code) |
| `asset_conditions` | code, name, is_usable b, severity i, description, sort_order | uq(company_id, code) |
| `asset_statuses` | code, name, system_state s32, is_default b, color s32, description, sort_order | uq(company_id, code); ix(company_id, system_state) |

### 15.2 `assets`
`asset_code` s64 · `asset_code_norm` s64 · `name` s · `category_id` fk · `unit_id` fk · `brand` s · `model` s ·
`serial_number` s128 · `serial_number_norm` s128 (NULL bila kosong) · `acquisition_date` s32 · `acquisition_year` i ·
`acquisition_value` dec(18,2) · `project_id` fk · `work_location_id` fk · `condition_id` fk · `status_id` fk ·
`lifecycle_state` s32 · `current_holding_id` fk · `last_bast_id` fk · `notes` t · `source` s32 (UI/IMPORT) · `row_version` i

Index: **uq(company_id, asset_code_norm)**, **uq(company_id, serial_number_norm)**, ix(company_id, project_id,
lifecycle_state), ix(company_id, category_id), ix(company_id, work_location_id), ix(company_id, lifecycle_state).

### 15.3 `asset_holdings`
`asset_id` fk · `employee_id` fk · `project_id` fk · `work_location_id` fk · `start_date` s32 · `start_date_known` b ·
`end_date` s32 · `holding_status` s32 (ACTIVE / ENDED / CANCELLED) · `source` s32 (HANDOVER / OPENING_BALANCE) ·
`handover_bast_id` fk · `return_bast_id` fk · `existing_bast_id` fk · `condition_out_id` fk · `condition_in_id` fk ·
`accessories_out` json · `accessories_in` json · **`active_lock` s64** (= asset_id saat ACTIVE, NULL lainnya)

Index: **uq(company_id, active_lock)**, ix(company_id, employee_id, holding_status), ix(company_id, asset_id, start_date),
ix(company_id, project_id, holding_status).

### 15.4 `asset_bast` (header dokumen/transaksi)
`bast_type` s32 (HANDOVER / RETURN / EXISTING) · `existing_mode` s32 (REFERENCE / CONFIRMATION, khusus EXISTING) ·
`system_number` s64 (NULL saat DRAFT) · `sequence_key` s64 · `sequence_period` s16 · `manual_number` s128 ·
`manual_number_norm` s128 · `bast_date` s32 · `employee_id` fk · `project_id` fk · `work_location_id` fk ·
`ga_pic_user_id` fk · `doc_state` s32 (DRAFT / ISSUED / SIGNED / VOID) · `inspection_state` s32 (N/A / PENDING / COMPLETED;
RETURN) · `source` s32 (UI / IMPORT) · `import_batch_id` fk · `notes` t · `snapshot` json · `pdf_path` s512 ·
`pdf_version` i · `signed_document_id` fk · `issued_at` / `issued_by` · `signed_at` · `void_reason` t · `voided_at` /
`voided_by` · `row_version` i

Index: **uq(company_id, system_number)**, ix(company_id, manual_number_norm), ix(company_id, bast_type, bast_date),
ix(company_id, employee_id, bast_date), ix(company_id, project_id, doc_state), ix(company_id, inspection_state).

### 15.5 `asset_bast_items` (item transaksi)
`bast_id` fk · `line_no` i · `asset_id` fk · `holding_id` fk · `asset_snapshot` json (kode, nama, merk, tipe, SN, satuan) ·
`condition_id` fk (kondisi serah / kembali) · `accessories` json · `accessories_note` t · `item_notes` t · `damage_notes` t ·
`inspection_status` s32 (N/A / PENDING / DONE) · `inspection_result_state` s32 · `inspection_condition_id` fk ·
`inspected_by` fk · `inspected_at` dt · `inspection_notes` t

Index: uq(company_id, bast_id, asset_id), ix(company_id, asset_id), ix(company_id, inspection_status, created_at).

### 15.6 `asset_events` (append-only; tidak ada endpoint update/delete)
`asset_id` fk · `event_type` s32 (CREATED, UPDATED_MASTER, IMPORTED, STATUS_CHANGE, RELOCATION, HANDOVER, RETURN,
INSPECTION, OPENING_BALANCE, BAST_ISSUED, BAST_SIGNED, BAST_VOID, HOLDING_CANCELLED) · `event_at` dt · `actor_user_id` fk ·
`from_state` / `to_state` s32 · `employee_id` fk · `project_id` fk · `work_location_id` fk · `condition_id` fk ·
`holding_id` fk · `bast_id` fk · `system_number` s64 · `manual_number` s128 · `changes` json · `notes` t

Index: ix(company_id, asset_id, event_at), ix(company_id, employee_id, event_at), ix(company_id, event_type, event_at).

### 15.7 Penomoran generik
| Tabel | Kolom | Index |
|---|---|---|
| `document_sequence_configs` | sequence_key s64, label s, format s128, reset_policy s16 (YEARLY / NEVER), is_system b | uq(company_id, sequence_key) |
| `document_sequence_counters` | sequence_key s64, period_key s64, next_value bi | uq(company_id, sequence_key, period_key) |

### 15.8 Impor
| Tabel | Kolom | Index |
|---|---|---|
| `asset_import_batches` | import_type s32 (ASSET_MASTER / OPENING_HOLDING), file_name, file_hash s64, file_size, batch_status s32 (ANALYZED / COMMITTED / PARTIAL / FAILED / EXPIRED), counts json, uploaded_by, committed_by, committed_at | ix(company_id, import_type, created_at) |
| `asset_import_rows` | batch_id fk, row_no i, row_class s16, payload json, changes json, messages json, warnings json, target_asset_id fk, target_employee_id fk, commit_status s16 (PENDING / DONE / SKIPPED / FAILED), commit_error t | ix(company_id, batch_id, row_no) |

### 15.9 Non-tabel
- `rbac.py`: modul `asset` "Manajemen Aset" + 7 resource + role preset `ga_admin`, `ga_staff` + default permissions (tanpa logic berbasis nama role).
- `masters.py`: 4 master baru.
- `documents.py`: owner_type `asset`, `asset_bast` + checker scope.
- `nav.js` / `App.js`: grup menu **top-level "Manajemen Aset"** + routes `/modules/asset/*`; tab Aset di `EmployeeDetailPage.jsx` (read-only).
- Seed idempoten per tenant saat aktivasi modul: master default, status default per state, 4 sequence config.
- Migration m0012: dry-run → apply → rerun SKIP. Uji di `hris_dev`, lalu `hris_staging`. **Tidak pernah di production tanpa
  instruksi.**

---

## 16. Urutan implementasi per checkpoint (setiap CP: STOP untuk review)

| CP | Isi | Verifikasi wajib |
|---|---|---|
| **CP0 — Prasyarat** | Konfirmasi 01H & 01I sudah merge ke `main`. Branch baru `feature/phase-2a-asset-bast` dari `origin/main` terbaru. Salin blueprint ke repo sebagai dokumen audit | `git log` main memuat 01H + 01I; working tree bersih |
| **CP1 — Foundation** | m0012 (seluruh tabel §15), modul + RBAC + role GA, 4 master + seed, engine `doc_sequence` (+ uji konkurensi), `core/asset_lifecycle.py`, CRUD Master Asset (kode manual/otomatis, SN unik, ubah status, relokasi), detail + histori event, lampiran aset, scope 01I (list/404/create), menu + halaman Daftar/Detail/Pengaturan (master + penomoran) | targeted backend (unik kode/SN, auto-code, transisi ilegal 409, scope 404/filter, sequence paralel tanpa duplikat, **role kustom "HRGA Admin" dengan izin sama = hak sama**), menu top-level tampil hanya dengan izin, regression 01H + 01I, frontend compile |
| **CP2 — Penyerahan + BAST AST** | form Penyerahan multi-aset (draft/terbit), holding ACTIVE + `active_lock`, nomor AST, snapshot, PDF, signed copy, nomor manual + warning duplikat, VOID, register BAST | test atomik multi-item, 2 penyerahan paralel aset sama → 1 sukses, A→B ditolak, scope 3 arah, nomor unik paralel |
| **CP3 — Pengembalian + Pemeriksaan + BAST RTN** | pengembalian parsial, periksa langsung / Menunggu Pemeriksaan, antrean pemeriksaan, inspection_state, regenerasi PDF sebelum SIGNED | test parsial (sisa tetap IN_USE), PENDING → hasil, tidak bisa diserahkan saat PENDING, histori tidak ditimpa |
| **CP4 — Profil 360 + Dashboard** | tab Aset read-only (sumber data = modul Manajemen Aset yang sama; tanpa transaksi di profil), badge outstanding, helper `outstanding_assets`, dashboard widget §13 | tab tidak punya endpoint tulis; scope (redaksi gaya atasan 01I); angka dashboard sesuai data uji |
| **CP5 — Impor Master Asset** | template, analisis 5 kelas, pratinjau per field, commit hash, riwayat | semua kelas + no silent overwrite + 403 restricted |
| **CP6 — Impor Saldo Awal + BAST EXS** | OPENING_BALANCE, BAST EXS REFERENCE (dikelompokkan per karyawan + nomor manual), BAST Konfirmasi Existing (per karyawan / massal) + PDF | tanpa event HANDOVER palsu, idempoten re-upload, conflict holder aktif |
| **CP7 — Export** | 7 export + filter + izin nilai perolehan | scope-aware (restricted hanya project-nya), kolom nomor sistem + manual |
| **CP8 — Regression & staging** | regression 01B–01I + 2A; m0012 di `hris_staging`; staging E2E (browser) dengan fixture sintetis; cleanup; LOCK | 2A LOCKED ✅ |

Estimasi relatif: CP1 terbesar, CP2–CP3 sedang-besar, CP4–CP7 sedang. Git hygiene: commit lokal per CP. Push/PR hanya atas
instruksi.

---

## 17. Risiko & mitigasi (final)

| Risiko | Mitigasi |
|---|---|
| Nomor BAST ganda saat paralel | counter FOR UPDATE di transaksi yang sama + unique index + retry; uji paralel di CP1/CP2 |
| Dua pemegang aktif | row-lock aset + `uq(active_lock)` di DB |
| Histori palsu saldo awal | OPENING_BALANCE bertanggal impor, `start_date_known`, tanpa HANDOVER |
| Pengembalian parsial membingungkan status BAST Penyerahan | status BAST Penyerahan tetap ISSUED/SIGNED; "sisa dipegang n / dikembalikan m" dihitung dari holding, bukan dari state header |
| Status configurable merusak lifecycle | `lifecycle_state` sistem otoritatif; status tenant hanya label |
| Kebocoran scope via dokumen/lampiran | checker scope owner_type aset di `documents.py`; UUID → 404 |
| Karyawan pindah project (01D) sementara aset tetap di project lama | aset tidak ikut otomatis; widget peringatan; return → handover formal |
| Format penomoran diubah menyebabkan tabrakan | validasi token + skip nomor terpakai + unique index |
| Nilai perolehan bocor | izin `asset_value` di API, UI, dan export |
| Role GA baru mempengaruhi matriks izin existing | penambahan aditif; role existing tidak berubah selain hak view aset untuk HR/finance |
| Logic terikat nama role (menghambat HRGA Admin) | larangan cek nama role; test: role kustom dengan izin identik GA Admin dapat melakukan seluruh alur |
| Profil 360 menjadi jalur transaksi kedua / data ganda | tab read-only, endpoint GET saja, service & tabel sama dengan modul |
| Ketergantungan merge 01H/01I | CP0 menahan coding sampai keduanya di `main` |

---

STOP — blueprint final selesai untuk review. Tidak ada coding, commit, push, PR, merge, atau deploy.
Production Changed: **NO**.
