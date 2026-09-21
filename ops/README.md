# Runtime development MariaDB

Runtime preview memakai folder standar `/app/backend` dan `/app/frontend`. MariaDB development tidak mengganti database engine dan tidak menyalin data produksi.

## Lokasi
- Konfigurasi server: `/app/ops/mariadb-dev.cnf`
- Konfigurasi supervisor: `/app/ops/payroll-dev-mariadb.conf`
- Data persisten: `/app/.local-data/mariadb`, diabaikan Git
- Env privat backend: `/app/backend/.env`

## Pemulihan proses (tanpa reset)
Setelah image/container dibangun ulang, pastikan paket `mariadb-server` dan `mariadb-client` tersedia. Pasang kembali salinan drop-in supervisor dari `/app/ops/payroll-dev-mariadb.conf` ke `/etc/supervisor/conf.d/`, kemudian jalankan `supervisorctl reread` dan `supervisorctl update`. Jangan inisialisasi ulang datadir yang sudah berisi database. Jalankan backend melalui supervisor, bukan uvicorn manual.

`python /app/backend/bootstrap_development.py` bersifat idempoten dan hanya menerima APP_ENV=development dengan database loopback/nama sesuai DEVELOPMENT_DB_NAME. Tidak mengganti kata sandi akun existing, tidak mereset matriks role, tidak membuat data bisnis contoh. AUTO_SEED wajib false; ENABLE_SCHEDULER=false. Gunakan DEV_ADMIN_EMAIL dan DEV_ADMIN_PASSWORD dari environment.

Jangan menjalankan script `test_core.py` lama dari repo: script tersebut berasal dari bootstrap integrasi produksi. Gunakan test_development_core.py dan suite tahap1 yang memiliki guard development.

R2 development belum tersedia. Jangan menyalin kunci produksi. Accounting ditunda. Ini runtime preview development, bukan pernyataan siap deploy produksi.
