# AGENTS.md — Aturan Kerja Repository

> **Dokumen ini mengikat siapa pun yang mengubah repository ini — manusia maupun AI agent.**
>
> **Tujuannya satu:** setiap perubahan masuk lewat **Pull Request** yang rapi, sehingga **apa yang ditambah dan apa yang dikurangi terlihat jelas dan bisa direview.**

Repository: `akuntakitatech-design/Payroll`
Branch utama: `main`
Berlaku sejak: PR #4

---

## 0. Ringkasan Satu Halaman

Kalau Anda hanya punya 30 detik, patuhi 7 hal ini:

| # | Aturan | Konsekuensi bila dilanggar |
|---|--------|----------------------------|
| 1 | **JANGAN push langsung ke `main`.** Selalu lewat branch + Pull Request. | Perubahan tidak bisa direview, riwayat kotor |
| 2 | **JANGAN commit `.env`**, PAT, password, atau kunci apa pun. | Kebocoran kredensial produksi |
| 3 | **Data produksi = HANYA-BACA** kecuali ada izin tertulis eksplisit. | Data asli perusahaan rusak/hilang |
| 4 | **Satu PR = satu tujuan.** Jangan campur fitur, perbaikan, dan rapikan kode. | Review jadi tidak mungkin |
| 5 | **Pindai diff terhadap secret** sebelum commit. | Kebocoran kredensial |
| 6 | **Tulis body PR lengkap** (lihat template Bagian 6). | PR ditolak |
| 7 | **JANGAN ubah** `REACT_APP_BACKEND_URL` dan `MONGO_URL`/`DATABASE_URL` milik lingkungan. | Integrasi frontend–backend rusak |

---

## 1. Konteks: Bagaimana Pemilik Repo Bekerja

Pahami pola kerja ini supaya Anda tidak salah asumsi:

1. **Pemilik repo akan selalu memberikan GitHub PAT** di awal sesi.
   PAT itu adalah **alat kerja, bukan bahan commit**. Dipakai untuk `clone`, `push`, dan membuat PR — titik.

2. **Pemilik repo akan selalu memberikan ENV PRODUCTION** (kredensial MariaDB, kunci Cloudflare R2, `JWT_SECRET`, domain, dll).
   Ini diberikan agar aplikasi **bisa dijalankan dan dilihat**, **bukan** izin untuk mengubah data produksi.
   Perlakukan sebagai **rahasia tingkat tertinggi**.

3. **Setiap kali menyimpan pekerjaan, pemilik repo meminta dibuatkan Pull Request.**
   "Save" dalam kamus repo ini berarti: **branch → commit → push → Pull Request**.
   Tidak ada "save" yang berupa push langsung ke `main`.

4. **Nomor PR selalu melanjutkan yang terakhir.** Kalau PR terakhir #4, maka PR berikutnya #5.
   Wajib cek dulu, jangan menebak (lihat Bagian 5.1).

5. **Bahasa kerja adalah Bahasa Indonesia** — judul PR, body PR, pesan commit, komentar kode, dan pesan error yang dilihat pengguna.

---

## 2. Aturan Kredensial (Tidak Bisa Ditawar)

### 2.1 Yang WAJIB dilakukan

- Simpan semua kredensial **hanya** di `backend/.env` (lokal, tidak pernah di-commit).
- Pastikan `.env` ada di `.gitignore` **sebelum** commit pertama.
- Kalau menambah variabel env baru, **dokumentasikan di `backend/.env.example`** dengan **nilai placeholder**, bukan nilai asli.
- Baca env lewat `os.environ.get(...)` di backend dan `process.env....` di frontend. **Tidak ada hardcode.**

### 2.2 Yang DILARANG

- ❌ Commit `.env`, `.env.local`, `.env.production`, atau turunannya.
- ❌ Menulis PAT, password DB, kunci R2, atau `JWT_SECRET` ke dalam **kode, komentar, pesan commit, body PR, README, atau berkas test**.
- ❌ Mencetak (`print`/`console.log`) atau menulis kredensial ke log.
- ❌ Menaruh kredensial di dalam `docker-compose.yml` yang ter-commit.
- ❌ Mengembalikan kredensial di response API, sekalipun untuk debugging.

### 2.3 Wajib: Pindai Secret Sebelum Commit

Jalankan ini **setiap kali** sebelum `git commit`:

```bash
git add -A

# 1) Pastikan tidak ada berkas .env yang ikut
git diff --cached --name-only | grep -E '(^|/)\.env' \
  && echo "BAHAYA: berkas .env ikut ter-stage!" \
  || echo "OK: tidak ada .env"

# 2) Pindai isi diff terhadap pola kredensial
git diff --cached | grep -n -Ei \
  'github_pat_|ghp_|AKIA|BEGIN [A-Z ]*PRIVATE KEY|password\s*=\s*[^ ]|secret\s*=\s*[^ ]|[0-9]{1,3}(\.[0-9]{1,3}){3}' \
  && echo "TINJAU TEMUAN DI ATAS SEBELUM LANJUT" \
  || echo "AMAN: tidak ada pola secret"
```

Kalau ada temuan, **perbaiki dulu**. Jangan commit "nanti diperbaiki".

### 2.4 Kalau Kredensial Sudah Bocor

Jangan panik, jangan disembunyikan. Lakukan berurutan:

1. **Laporkan segera** ke pemilik repo — jangan tunggu ditanya.
2. **Rotasi kredensialnya** (ganti PAT, password DB, kunci R2, `JWT_SECRET`). Menghapus commit **tidak** membuat kredensial aman kembali — anggap sudah bocor permanen.
3. Baru setelah itu bersihkan riwayat git bila diperlukan.

---

## 3. Aturan Data Produksi: HANYA-BACA secara Default

Repo ini terhubung ke infrastruktur produksi nyata:

- **MariaDB** produksi (via Coolify) — berisi data karyawan, kontrak, gaji, dan dokumen asli.
- **Cloudflare R2** bucket `media-akunkita` — berisi dokumen asli karyawan.

### 3.1 Aturan

- Saat menjalankan aplikasi di lingkungan **non-produksi** (lokal, live preview, staging) yang menunjuk ke **data produksi**, **WAJIB** set:

  ```ini
  READ_ONLY=true
  AUTO_SEED=false
  ```

- `READ_ONLY=true` akan memblokir seluruh `INSERT`/`UPDATE`/`DELETE` (HTTP **423 Locked**), memblokir upload/hapus objek R2, melewati seluruh DDL/sinkronisasi skema, serta menonaktifkan seed data dan penjadwal email.
- Verifikasi mode aktif sebelum mulai bekerja:

  ```bash
  curl -s "$BASE_URL/api/system/mode"
  # harus mengembalikan {"read_only": true, ...}
  ```

### 3.2 Yang DILARANG tanpa izin tertulis eksplisit

- ❌ Menjalankan `DROP`, `TRUNCATE`, `ALTER`, atau migrasi apa pun terhadap database produksi.
- ❌ Menyalakan `AUTO_SEED=true` saat menunjuk ke database produksi (data demo akan mengotori data asli).
- ❌ Menghapus atau menimpa objek di bucket R2 produksi.
- ❌ Menjalankan penjadwal pengingat email saat menunjuk data produksi (email akan benar-benar terkirim ke penerima asli).
- ❌ Mengubah, mereset, atau membuat user/password di tabel `users` produksi.

### 3.3 Kalau Butuh Menguji Operasi Tulis

Jangan pernah menguji di produksi. Pilih salah satu, dan **minta persetujuan dulu**:

1. Database salinan terpisah hasil clone dari produksi (mis. `hris_preview`).
2. Database lokal/kosong dengan `AUTO_SEED=true`.
3. Prefix R2 terpisah (mis. `R2_PREFIX=hris-preview`) agar berkas tidak bercampur.

---

## 4. Aturan Branch & Commit

### 4.1 Penamaan Branch

Format: `<tipe>/<deskripsi-singkat-kebab-case>`

| Tipe | Kapan dipakai | Contoh |
|------|---------------|--------|
| `feature/` | Fitur atau kemampuan baru | `feature/readonly-production-preview` |
| `fix/` | Perbaikan bug | `fix/login-error-message` |
| `docs/` | Hanya dokumentasi | `docs/aturan-kerja-repo` |
| `refactor/` | Rapikan kode, perilaku tidak berubah | `refactor/pisah-router-payroll` |
| `chore/` | Dependensi, konfigurasi, perkakas | `chore/naikkan-versi-sqlalchemy` |

Aturan tambahan:
- Selalu buat branch dari `main` yang **sudah ter-update** (`git pull`).
- Satu branch = satu tujuan. Kalau di tengah jalan menemukan hal lain, **buat branch baru**.
- Jangan pakai nama branch generik seperti `update`, `patch`, `baru`, atau `test`.

### 4.2 Format Pesan Commit

Pakai **Conventional Commits** dengan isi Bahasa Indonesia:

```
<tipe>(<ruang-lingkup opsional>): <ringkasan, maksimal ~72 karakter>

<badan: JELASKAN ALASAN, bukan sekadar apa yang diubah>

Perubahan:
- berkas/modul : apa yang berubah dan mengapa
- berkas/modul : apa yang berubah dan mengapa

Catatan: <dampak, batasan, atau hal yang perlu diwaspadai reviewer>
```

Contoh nyata dari repo ini:

```
feat: mode HANYA-BACA (READ_ONLY) untuk menjalankan app dengan data produksi secara aman

Menambahkan sakelar READ_ONLY agar aplikasi dapat dijalankan di lingkungan
non-produksi sambil terhubung ke MariaDB dan R2 PRODUKSI, tanpa risiko
mengubah data asli.

Perubahan:
- core/config.py : setting READ_ONLY + READ_ONLY_SILENT_TABLES
- core/db.py     : guard pada seluruh jalur tulis, DDL dilewati saat aktif
- server.py      : endpoint GET /api/system/mode, seed & scheduler off

Catatan: tulisan ke tabel users/audit_logs di-no-op tanpa error supaya
alur login tetap berfungsi normal.
```

Aturan tambahan:
- Ringkasan memakai kalimat perintah ("tambahkan", "perbaiki"), bukan masa lalu ("menambahkan sudah").
- **Jangan** pakai pesan tak bermakna: `update`, `fix`, `wip`, `asdf`, `perubahan kecil`.
- Satu commit sebaiknya satu perubahan logis yang utuh.

---

## 5. Aturan Pull Request

### 5.1 Wajib: Cek Nomor PR Terakhir Dulu

Nomor PR harus melanjutkan yang terakhir. **Cek, jangan menebak:**

```bash
export GH=<PAT_DARI_PEMILIK_REPO>

curl -s -H "Authorization: Bearer $GH" \
  "https://api.github.com/repos/akuntakitatech-design/Payroll/pulls?state=all&per_page=100" \
  | python3 -c "
import sys, json
d = json.load(sys.stdin)
for p in d:
    print('PR #%s [%s] %s -> %s | %s' % (p['number'], p['state'], p['head']['ref'], p['base']['ref'], p['title'][:60]))
print('PR terakhir: #%s  =>  PR berikutnya: #%s' % (d[0]['number'], d[0]['number'] + 1) if d else 'Belum ada PR => mulai dari #1')
"
```

### 5.2 Alur Lengkap Membuat PR

```bash
# 1. Mulai dari main yang ter-update
git checkout main && git pull

# 2. Branch baru sesuai konvensi
git checkout -b feature/nama-yang-jelas

# 3. Kerjakan perubahan...

# 4. WAJIB: pindai secret (lihat Bagian 2.3)
git add -A
git diff --cached --name-only | grep -E '(^|/)\.env' && echo "STOP: ada .env!"

# 5. Commit dengan format yang benar
git commit -F pesan-commit.txt

# 6. Push (PAT tidak pernah disimpan di remote config)
git push "https://x-access-token:${GH}@github.com/akuntakitatech-design/Payroll.git" \
  feature/nama-yang-jelas

# 7. Buat PR lewat API
curl -s -X POST \
  -H "Authorization: Bearer $GH" \
  -H "Accept: application/vnd.github+json" \
  "https://api.github.com/repos/akuntakitatech-design/Payroll/pulls" \
  -d @pr.json
```

### 5.3 Syarat PR Diterima

Sebuah PR hanya boleh diajukan bila **semua** ini benar:

- [ ] Target branch adalah `main`
- [ ] Tidak ada berkas `.env` atau kredensial di dalam diff
- [ ] Diff sudah dipindai terhadap pola secret dan hasilnya bersih
- [ ] Satu PR hanya punya satu tujuan
- [ ] Judul PR memakai format Conventional Commits berbahasa Indonesia
- [ ] Body PR mengikuti template Bagian 6 dan **tidak dikosongkan**
- [ ] Ada tabel berkas yang diubah beserta alasannya
- [ ] Ada bagian **Verifikasi** yang menjelaskan bagaimana perubahan diuji
- [ ] Ada bagian **Keamanan** yang menyatakan tidak ada kredensial ter-commit
- [ ] Perubahan yang berisiko diberi catatan mencolok
- [ ] Status PR `mergeable: clean` (tidak ada konflik)
- [ ] Backend jalan tanpa error (`tail /var/log/supervisor/backend.err.log`)
- [ ] Frontend ter-build tanpa error import
- [ ] Semua endpoint baru memakai prefix `/api`

### 5.4 Yang DILARANG pada PR

- ❌ Push langsung ke `main` atau `force-push` ke `main`.
- ❌ Merge PR sendiri tanpa persetujuan pemilik repo.
- ❌ Body PR kosong atau hanya satu baris.
- ❌ PR raksasa yang mencampur banyak tujuan berbeda.
- ❌ Menyertakan `node_modules/`, `__pycache__/`, `build/`, atau berkas artefak.
- ❌ Mengubah berkas yang **tidak berkaitan** dengan tujuan PR (termasuk reformat massal yang membuat diff membengkak).
- ❌ Menyembunyikan perubahan berisiko di tengah PR tanpa catatan.

---

## 6. Template Body PR (Wajib Dipakai)

````markdown
## Ringkasan

<2–4 kalimat: apa yang diubah dan MENGAPA. Reviewer harus paham tanpa membaca kode.>

---

## Latar Belakang

<Masalah yang diselesaikan. Sertakan tabel risiko/gejala bila relevan.>

| Masalah | Dampak sebelum PR ini |
|---|---|
| ... | ... |

---

## Perubahan

### `path/ke/berkas.py`
- <perubahan spesifik dan alasannya>
- <perubahan spesifik dan alasannya>

### `path/ke/berkas-lain.js`
- <perubahan spesifik dan alasannya>

---

## Kompatibilitas

<Apakah ada breaking change? Apakah perilaku lama tetap sama?
Kalau menambah sakelar/flag, sebutkan nilai default-nya dan
tegaskan produksi tidak terpengaruh bila default dipakai.>

---

## Verifikasi

<Bagaimana perubahan ini diuji. Sertakan perintah nyata dan hasil yang diharapkan.>

```bash
# contoh perintah uji
curl -s "$BASE_URL/api/system/mode"
# -> {"read_only": true, ...}
```

Hasil:
- [ ] <hal yang sudah diverifikasi>
- [ ] <hal yang sudah diverifikasi>

**Belum diuji / di luar cakupan:** <sebutkan dengan jujur, jangan disembunyikan>

---

## Keamanan

- Tidak ada kredensial yang ter-commit. `backend/.env` tetap ada di `.gitignore`.
- Diff sudah dipindai terhadap PAT, password database, kunci R2, `JWT_SECRET`, dan alamat IP — hasilnya bersih.
- Hanya `.env.example` yang diubah, berisi placeholder saja.

---

## Risiko & Rencana Mundur (Rollback)

- **Risiko:** <apa yang bisa salah>
- **Rollback:** <cara mengembalikan, mis. revert commit / set flag ke false>

---

## Berkas yang Diubah

| Berkas | Perubahan |
|---|---|
| `path/ke/berkas.py` | <ringkasan singkat> |
````

---

## 7. Aturan Teknis Repo Ini

### 7.1 Arsitektur

| Lapisan | Teknologi | Catatan |
|---|---|---|
| Frontend | React 19 + CRA/CRACO + Tailwind + shadcn/ui | port `3000` |
| Backend | FastAPI + SQLAlchemy Core (async) | port `8001`, bind `0.0.0.0` |
| Database | MariaDB via `asyncmy` | adapter bergaya Mongo di `app/core/db.py` |
| Object storage | Cloudflare R2 (S3 compatible, `boto3`) | berkas **tidak pernah** disimpan di container |
| Deployment | Docker + Coolify | domain `hris.akuntakita.com` |

### 7.2 Aturan Backend

- **Semua** endpoint **wajib** berada di bawah prefix `/api` (syarat routing ingress).
- Jangan jalankan `uvicorn` manual; pakai supervisor (`supervisorctl restart backend`).
- Restart backend hanya perlu setelah mengubah `.env` atau dependensi (hot reload aktif).
- Pesan error yang dilihat pengguna ditulis dalam **Bahasa Indonesia** dan menjelaskan langkah perbaikan.
- Selalu tangani konversi tipe (`datetime`, `Decimal`) sebelum mengembalikan response JSON.
- Menambah dependensi: `pip install <paket>` lalu **tambahkan ke** `requirements.txt` (jangan tulis ulang berkasnya).

### 7.3 Aturan Frontend

- Panggil backend **hanya** lewat `process.env.REACT_APP_BACKEND_URL` + `/api/...`. **Tidak ada URL hardcode.**
- Menambah dependensi **wajib** pakai `yarn add`. **JANGAN pakai `npm`** — merusak `yarn.lock`.
- Setiap elemen interaktif diberi `data-testid` agar bisa diuji otomatis.
- Tangani seluruh state: *loading*, *empty*, *error*, dan *success*.
- **Jangan pakai background transparan** pada komponen dengan teks gelap (pengguna bisa memakai tema terang maupun gelap).

### 7.4 Variabel Lingkungan yang TIDAK BOLEH Diubah

Variabel berikut disetel oleh platform/lingkungan. **Mengubahnya akan merusak aplikasi:**

- `frontend/.env` → `REACT_APP_BACKEND_URL`
- `backend/.env` → `DATABASE_URL` / `MONGO_URL` yang disediakan lingkungan

Kalau butuh nilai berbeda, **minta ke pemilik repo**, jangan diubah sendiri.

### 7.5 Berkas yang Perlu Kehati-hatian Ekstra

| Berkas | Mengapa berisiko |
|---|---|
| `backend/app/core/db.py` | Adapter database inti; salah ubah merusak seluruh router |
| `backend/app/core/storage.py` | Menyentuh bucket R2 produksi |
| `backend/app/seed.py` | Bisa menulis data demo ke database produksi |
| `backend/app/core/scheduler.py` | Bisa mengirim email nyata ke penerima asli |
| `backend/app/core/payroll.py`, `ter.py` | Logika PPh 21 metode TER; salah hitung = salah bayar gaji |
| `requirements.txt`, `package.json`, `yarn.lock` | Tambah lewat perkakas resmi, jangan tulis ulang |

---

## 8. Kontrak Khusus untuk AI Agent

Selain seluruh aturan di atas, AI agent **wajib**:

1. **Bertanya sebelum bertindak** bila instruksi ambigu, terutama menyangkut data produksi. Lebih baik bertanya daripada merusak data asli.
2. **Melaporkan kegagalan dengan jujur.** Jangan pernah mengklaim sesuatu "sudah berfungsi" atau "sudah diuji" kalau belum benar-benar diverifikasi.
3. **Menyatakan secara eksplisit bila ada yang di-mock.** Tulis dengan **HURUF KAPITAL** di ringkasan bila ada data/integrasi yang masih tiruan.
4. **Tidak memperluas cakupan sendiri.** Kerjakan yang diminta; usulkan sisanya, jangan langsung dikerjakan.
5. **Tidak menebak nomor PR, versi paket, atau nama model.** Selalu verifikasi lewat API atau dokumentasi resmi.
6. **Tidak menyarankan "hapus cache" atau "coba mode incognito"** sebagai solusi bug autentikasi. Telusuri log backend dan bandingkan dengan implementasi rujukan.
7. **Menyertakan ringkasan perubahan** di akhir pekerjaan: apa yang berhasil, apa yang gagal, apa yang belum diuji.
8. **Menandai teks yang tampak salah ketik** sebelum menerapkannya (mis. nama produk yang berulang atau janggal) — terapkan sesuai permintaan, tetapi beri catatan agar bisa ditinjau.
9. **Menjaga konsistensi penamaan.** Kalau mengganti nama produk, cari **seluruh** kemunculannya (`grep -rn`) dan laporkan mana yang diubah dan mana yang sengaja dilewati.
10. **Tidak membagikan URL localhost** kepada pemilik repo — hanya URL preview/produksi yang bisa mereka akses.

---

## 9. Daftar Periksa Akhir Sebelum Mengajukan PR

Salin dan centang satu per satu:

```
KREDENSIAL
[ ] Tidak ada .env di dalam diff
[ ] Diff sudah dipindai terhadap pola secret, hasilnya bersih
[ ] Variabel env baru sudah didokumentasikan di .env.example (placeholder)
[ ] PAT tidak tersimpan di git remote config

DATA PRODUKSI
[ ] READ_ONLY=true dan AUTO_SEED=false saat menunjuk data produksi
[ ] Tidak ada DDL/migrasi yang dijalankan ke database produksi
[ ] Tidak ada objek R2 produksi yang ditimpa atau dihapus
[ ] Tidak ada email yang benar-benar terkirim

KODE
[ ] Satu PR = satu tujuan
[ ] Semua endpoint baru memakai prefix /api
[ ] Frontend memakai REACT_APP_BACKEND_URL, tidak ada URL hardcode
[ ] Dependensi ditambahkan lewat pip/yarn, bukan diedit manual
[ ] Backend jalan tanpa error di log
[ ] Frontend ter-build tanpa error import
[ ] Tidak ada artefak (node_modules, __pycache__, build) ikut ter-commit

PULL REQUEST
[ ] Nomor PR terakhir sudah dicek lewat API
[ ] Nama branch mengikuti konvensi
[ ] Pesan commit memakai Conventional Commits berbahasa Indonesia
[ ] Body PR lengkap sesuai template Bagian 6
[ ] Bagian Verifikasi terisi, termasuk yang BELUM diuji
[ ] Bagian Keamanan terisi
[ ] Risiko & rencana rollback tercantum
[ ] Status mergeable: clean
[ ] URL PR sudah dilaporkan ke pemilik repo
```

---

## 10. Penutup

Aturan ini ada supaya **pemilik repo selalu bisa melihat dengan jelas apa yang ditambah dan apa yang dikurangi**, dan supaya **data produksi perusahaan tetap aman**.

Kalau ragu: **berhenti dan bertanya.** Satu pertanyaan jauh lebih murah daripada satu data produksi yang rusak.

Kalau suatu aturan di dokumen ini menghalangi pekerjaan yang sah, **jangan dilanggar diam-diam** — ajukan perubahan aturannya lewat PR tersendiri, agar bisa direview seperti perubahan lainnya.
