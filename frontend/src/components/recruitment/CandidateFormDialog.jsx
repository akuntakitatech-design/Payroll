import React, { useMemo } from "react";
import FormDialog from "@/components/common/FormDialog";

/**
 * Form tambah/ubah kandidat. Dipakai di Daftar Kandidat dan Detail Kandidat
 * agar field selalu konsisten. Semua pilihan master berasal dari
 * GET /recruitment/catalog (master existing, tanpa duplikasi).
 */
export const CandidateFormDialog = ({
  open,
  onOpenChange,
  mode = "create",
  catalog,
  values,
  errors,
  onChange,
  onSubmit,
  submitting,
}) => {
  const opt = (key) => (catalog?.[key] || []).map((o) => ({ value: o.id, label: o.name }));
  const keyOpt = (key) => (catalog?.[key] || []).map((o) => ({ value: o.key, label: o.label }));

  const fields = useMemo(
    () => [
      { name: "full_name", label: "Nama Lengkap", required: true, placeholder: "Nama sesuai KTP", colSpan: 2 },
      {
        name: "candidate_number",
        label: "Nomor Kandidat",
        placeholder: "Otomatis bila dikosongkan",
        hint: mode === "create" ? "Kosongkan agar sistem membuat nomor otomatis (CND-<tahun>-0001)." : undefined,
      },
      { name: "nik", label: "NIK (KTP)" },
      { name: "gender", label: "Jenis Kelamin", type: "select", options: keyOpt("genders") },
      { name: "birth_place", label: "Tempat Lahir" },
      { name: "birth_date", label: "Tanggal Lahir", type: "date" },
      { name: "phone", label: "No. HP / WhatsApp", placeholder: "08xxxxxxxxxx" },
      { name: "email", label: "Email", placeholder: "nama@email.com" },
      { name: "city", label: "Kota Domisili" },
      { name: "address", label: "Alamat", type: "textarea", colSpan: 2 },
      // --- lamaran ---
      { name: "position_id", label: "Posisi yang Dilamar", type: "select", options: opt("positions") },
      { name: "applied_position_title", label: "Sebutan Posisi (opsional)", placeholder: "Jika belum ada di master jabatan" },
      { name: "department_id", label: "Departemen", type: "select", options: opt("departments") },
      { name: "work_location_id", label: "Lokasi Kerja", type: "select", options: opt("work_locations") },
      { name: "project_id", label: "Proyek", type: "select", options: opt("projects") },
      { name: "source", label: "Sumber Kandidat", type: "select", options: keyOpt("sources") },
      { name: "source_detail", label: "Detail Sumber", placeholder: "Nama perujuk / portal" },
      { name: "applied_at", label: "Tanggal Masuk Kandidat", type: "date" },
      { name: "expected_salary", label: "Ekspektasi Gaji (Rp)", type: "number" },
      { name: "available_from", label: "Siap Bekerja Mulai", type: "date" },
      // --- pendidikan & pengalaman ---
      { name: "last_education", label: "Pendidikan Terakhir", type: "select", options: keyOpt("educations") },
      { name: "major", label: "Jurusan" },
      { name: "institution", label: "Institusi" },
      { name: "graduation_year", label: "Tahun Lulus", type: "number" },
      { name: "last_company", label: "Perusahaan Terakhir" },
      { name: "last_position", label: "Posisi Terakhir" },
      { name: "experience_years", label: "Lama Pengalaman (tahun)", type: "number" },
      { name: "notes", label: "Catatan HR", type: "textarea", colSpan: 2 },
    ],
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [catalog, mode]
  );

  return (
    <FormDialog
      open={open}
      onOpenChange={onOpenChange}
      title={mode === "create" ? "Tambah Kandidat" : "Ubah Data Kandidat"}
      description={
        mode === "create"
          ? "Kandidat baru masuk sebagai Draft. Posisi, departemen, lokasi, dan proyek memakai master data perusahaan aktif."
          : "Perubahan tercatat di Audit Log. Status tahapan diubah lewat aksi proses, bukan dari form ini."
      }
      fields={fields}
      values={values}
      errors={errors}
      onChange={onChange}
      onSubmit={onSubmit}
      submitting={submitting}
      submitLabel={mode === "create" ? "Simpan Kandidat" : "Simpan Perubahan"}
      wide
    />
  );
};

export default CandidateFormDialog;
