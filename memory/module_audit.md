# Audit modul HRIS / Payroll — Tahap 1

## Lingkup dan bukti
Audit source dilakukan dan ringkasan ditampilkan kepada pemilik SEBELUM perubahan tahap ini. Acuan kode main 8255f1b yang diimpor, 20 commit pada commit_review.md. Tidak mengakses produksi untuk audit lanjutan ini. Aktivasi produksi hanya berdasarkan tangkapan layar pengguna, bukan pembacaan baru database.

| Kelompok | Modul | Bukti / batasan |
|---|---|---|
| A: Implementasi operasional existing, aktif menurut screenshot | HR Core; Karyawan termasuk kontrak/sertifikasi; Payroll termasuk BPJS/PPh21 | Router dan UI tersedia. Belum merupakan klaim semua fungsi teruji; regresi dilakukan di database development |
| B: Terdaftar tetapi placeholder | recruitment, attendance, leave_overtime, performance, mobilization, finance_request | MODULES/RESOURCES di rbac.py, NAV_GROUPS/MODULE_INFO di nav.js, route generic ModulePlaceholderPage |
| C: Tidak aktif pada screenshot | Rekrutmen, KPI, Mobilisasi, Permintaan Keuangan, Akuntansi | Aktivasi per perusahaan; tidak diubah pada produksi |
| D: Belum tersedia operasional | Portal pelamar, verifikasi/pipeline/interview/offering/konversi; absensi GPS/shift; saldo/pengajuan cuti; KPI; batch mobilisasi/demobilisasi; transaksi finance | Belum ada router/tabel domain. Akuntansi sengaja ditunda |

## Fondasi yang dipakai kembali
- 38 tabel existing: 7 global dan 31 tenant. Tidak perlu tabel baru untuk tahap struktur.
- Katalog 10 modul, permission per resource/action, default_role_permissions, tenant DB accessor dan company_modules existing.
- Endpoint aktivasi GET /api/modules dan PUT /api/modules/toggle sudah ada.
- Route /modules/:moduleKey dan menu untuk keenam modul sudah ada: jangan diduplikasi.
- Kontrak dan sertifikasi terhubung profil karyawan, dokumen dan kalender masa berlaku.
- Approval workflow/steps, policies/config_overrides, audit_logs, master proyek/lokasi tersedia.
- Mesin payroll/BPJS/TER/progresif dan snapshot konfigurasi sudah ada. Jangan ubah rumus atau mengklaim kepatuhan pajak lengkap; tax-rule versioning, Gross/Net/Gross Up penuh dan Locked merupakan backlog yang perlu analisis terpisah.

## Gap tahap struktur
1. Halaman placeholder memeriksa aktivasi tetapi belum permission saat URL diakses langsung.
2. UI aktivasi belum membedakan akses aktif vs kesiapan operasional.
3. Placeholder generik belum menunjukkan struktur proses dan koneksi reuse spesifik modul.
4. Akuntansi masih dapat ditoggle walaupun ditunda: tahap ini UI harus menyatakan ditunda, tanpa business logic akuntansi.
5. Runtime masih menggunakan koneksi produksi pada tahap bootstrap lama: hentikan dan ganti dengan MariaDB development terpisah sebelum development/testing baru.

## Perubahan yang disetujui untuk tahap ini
- MariaDB development loopback terpisah; akun admin DEVELOPMENT dengan password acak dari env; hanya katalog sistem dan tenant development, tanpa seed data bisnis.
- Metadata fondasi per modul dan endpoint baca yang memakai RBAC/aktivasi existing; tanpa tabel transaksi baru atau perubahan kontrak endpoint lama.
- Lengkapi halaman placeholder existing, pertahankan route/sidebar/font/warna, label operasional belum dibangun, tautan ke fitur existing difilter permission.
- Tambah status kesiapan pada aktivasi tanpa mengubah permission matrix atau logika payroll.
- Uji build, login development, aktivasi per tenant, izin, tanpa duplikasi, dan regresi existing. STOP setelah laporan.

## Di luar tahap ini
Seluruh business logic rinci pada 30 bagian spesifikasi pemilik; integrasi GPS/perangkat, kanal notifikasi, unggah kandidat, transaksi finance, kalkulasi pajak baru, Accounting. R2 development belum diberikan: jangan gunakan R2 produksi, jangan mock storage.
