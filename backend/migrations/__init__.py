"""Migrasi data/skema berversi (additive, idempotent).

Aturan:
- Hanya ADDITIVE: tambah tabel/kolom/index/baris referensi. Dilarang DROP/RENAME/ubah tipe.
- Idempotent: aman dijalankan berulang (staging lalu produksi dengan file yang SAMA).
- Default DRY-RUN; perubahan hanya ditulis dengan flag --apply.

Pemakaian (dari folder backend):
    python -m migrations.m0001_tenant_foundation            # dry-run
    python -m migrations.m0001_tenant_foundation --apply    # terapkan
"""
