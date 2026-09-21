// Metadata struktur saja; bukan transaksi, aturan perusahaan, atau mesin proses baru.
export const MODULE_FOUNDATIONS = {
  recruitment: {
    flow: "Pelamar baru → Verifikasi HR → Seleksi → Penawaran kerja → Karyawan",
    focus: "HR fokus pada data belum lengkap, potensi duplikasi, dan keputusan seleksi. Pelamar mengisi data sendiri; data terverifikasi digunakan kembali saat menjadi karyawan.",
    sections: [
      ["Sumber kandidat", "Portal pelamar mandiri, input HR, serta impor Excel/CSV dengan pemetaan dan validasi."],
      ["Verifikasi awal", "Periksa kelengkapan, kualifikasi minimum, duplikasi, dan permintaan perbaikan sebelum masuk seleksi."],
      ["Tahapan seleksi & wawancara", "Tahapan dan indikator penilaian dapat dikonfigurasi per perusahaan; daftar dan tampilan alur seleksi."],
      ["Penawaran & karyawan", "Penawaran kerja dan konversi kandidat menggunakan biodata, dokumen, jabatan, proyek, serta kontrak tanpa input ulang."],
    ],
    dependencies: ["/setup/positions", "/setup/work-locations", "/setup/document-types", "/employees", "/setup/approval-workflows"],
  },
  attendance: {
    flow: "Jadwal kerja → Masuk / Pulang → Pemeriksaan pengecualian → Rekap",
    focus: "HR menangani keterlambatan, kehadiran tidak lengkap, dan koreksi. Kehadiran normal tidak perlu diperiksa satu per satu.",
    sections: [
      ["Shift & jadwal", "Struktur jadwal kerja terhubung dengan lokasi dan karyawan existing."],
      ["Masuk & pulang", "Tahap berikutnya menggunakan GPS, radius lokasi, dan waktu server; belum ada pencatatan kehadiran pada tahap ini."],
      ["Koreksi & audit", "Koreksi HR wajib memiliki alasan, aktor, waktu, dan histori perubahan."],
      ["Rekap & sumber data", "Siap dikembangkan untuk web/ponsel, impor, API perangkat, dan manual HR tanpa terikat vendor. Face recognition dan fingerprint ditunda."],
    ],
    dependencies: ["/employees", "/setup/work-locations", "/setup/policies", "/audit-logs"],
  },
  leave_overtime: {
    flow: "Saldo & kebijakan → Pengajuan → Persetujuan → Histori & rekap",
    focus: "Gunakan data karyawan dan alur persetujuan existing. HR menangani pengajuan yang memerlukan keputusan, benturan jadwal, dan koreksi saldo.",
    sections: [
      ["Jenis & saldo cuti", "Jenis cuti, kuota, dan kebijakan yang dapat berbeda antar perusahaan."],
      ["Cuti, izin & sakit", "Pengajuan karyawan, lampiran, status keputusan, dan histori."],
      ["Lembur", "Pengajuan dan realisasi lembur untuk ditinjau melalui persetujuan existing."],
      ["Rekap ke payroll", "Rencana integrasi saldo, ketidakhadiran, dan lembur; belum mengubah perhitungan payroll existing."],
    ],
    dependencies: ["/employees", "/setup/policies", "/setup/approval-workflows", "/payroll/runs"],
  },
  performance: {
    flow: "Periode & indikator → Target → Realisasi → Tinjauan atasan → Hasil akhir",
    focus: "Indikator tidak dikunci dalam kode. Tinjauan difokuskan pada target belum tercapai, penilaian yang belum lengkap, dan keputusan atasan.",
    sections: [
      ["Periode & indikator", "Indikator, satuan, bobot, dan periode penilaian dapat dikonfigurasi."],
      ["Hierarki target", "Struktur untuk KPI perusahaan, divisi, tim, dan individu menggunakan organisasi existing."],
      ["Realisasi & penilaian", "Pencatatan realisasi dan perhitungan nilai sesuai konfigurasi yang akan disepakati."],
      ["Tinjauan & histori", "Tinjauan atasan, hasil akhir, dan histori; tidak mengubah gaji secara otomatis pada tahap ini."],
    ],
    dependencies: ["/setup/divisions", "/setup/departments", "/setup/positions", "/employees", "/setup/approval-workflows"],
  },
  mobilization: {
    flow: "Penempatan proyek → Batch mobilisasi → Kebutuhan dana → Demobilisasi",
    focus: "Gunakan kembali data karyawan, lokasi, proyek, kontrak, dan sertifikasi. Fokus pada persyaratan yang belum lengkap serta biaya yang perlu persetujuan.",
    sections: [
      ["Penempatan & asal", "Home base, kota asal, lokasi rekrutmen, lokasi penempatan, proyek, dan periode penugasan."],
      ["Batch mobilisasi", "Penempatan banyak karyawan dengan moda transportasi dan jenis biaya yang dapat dikonfigurasi."],
      ["Rekap kebutuhan dana", "Rencana rekap orang, tiket, akomodasi, transportasi lokal, dan pengajuan ke Finance tanpa input ulang."],
      ["Demobilisasi", "Rencana pemulangan, estimasi dan realisasi biaya, serta histori penempatan."],
    ],
    dependencies: ["/employees", "/setup/projects", "/setup/work-locations", "/reminders", "/setup/approval-workflows"],
  },
  finance_request: {
    flow: "Pengajuan → Persetujuan → Pembayaran → Pertanggungjawaban → Realisasi",
    focus: "Finance meninjau kebutuhan persetujuan, kelengkapan bukti, dan selisih anggaran. Modul ini tetap dirancang berjalan tanpa Akuntansi.",
    sections: [
      ["Jenis pengajuan", "Kasbon, penggantian biaya, permintaan dana, mobilisasi, dan demobilisasi."],
      ["Sumber pembayaran", "Pembayaran vendor, uang muka PIC, transfer karyawan, atau penggantian biaya."],
      ["Persetujuan & bukti", "Gunakan alur persetujuan dan arsip dokumen existing, bukan mesin persetujuan baru."],
      ["Anggaran & realisasi", "Pertanggungjawaban, realisasi, dan selisih; integrasi potongan payroll menunggu tahap berikutnya."],
    ],
    dependencies: ["/employees", "/setup/projects", "/setup/cost-centers", "/documents", "/setup/approval-workflows"],
  },
};

export const moduleReadiness = (mod) => {
  if (mod.key === "accounting") return { label: "Ditunda", description: "Akuntansi opsional; tidak dikerjakan pada tahap ini." };
  if (MODULE_FOUNDATIONS[mod.key]) return { label: "Fondasi tersedia", description: "Struktur dan akses tersedia. Fitur operasional belum dibangun." };
  return { label: "Implementasi tersedia", description: "Modul yang sudah ada dipertahankan; tidak dibangun ulang." };
};

export const moduleAuditGroup = (mod) => {
  if (!mod.is_active) return "C · Belum aktif";
  if (MODULE_FOUNDATIONS[mod.key] || mod.status === "planned") return "B · Belum lengkap";
  return "A · Existing aktif";
};
