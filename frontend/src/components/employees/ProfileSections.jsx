import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Briefcase,
  Building2,
  CalendarDays,
  Camera,
  FileText,
  History,
  Loader2,
  MapPin,
  Pencil,
  Phone,
  Plus,
  ShieldCheck,
  Trash2,
  UserRound,
  Users,
} from "lucide-react";
import { toast } from "sonner";
import { api, errorMessage } from "@/lib/api";
import { formatDate } from "@/lib/format";
import FormDialog from "@/components/common/FormDialog";
import ConfirmDialog from "@/components/common/ConfirmDialog";
import { EmployeeStatusBadge } from "@/components/employees/EmployeeStatusBadge";
import StatusHistoryCard from "@/components/employees/StatusHistoryCard";
import { PhotoCropDialog } from "@/components/employees/PhotoCropDialog";
import { CATEGORY_LABELS } from "@/lib/employeeStatus";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";

/* ------------------------------------------------------------------ helpers */
const lbl = (list, key) => (list || []).find((o) => o.key === key)?.label || key || null;
const MAX_PHOTO_MB = 10;
const PHOTO_TYPES = ["image/jpeg", "image/png", "image/webp"];

export const InfoRow = ({ label, value, testId, mono = false }) => (
  <div className="grid grid-cols-1 gap-0.5 border-b border-border/60 py-2 last:border-0 sm:grid-cols-[12rem,1fr] sm:gap-4">
    <span className="text-[12px] text-muted-foreground">{label}</span>
    <span className={`break-words text-[13px] text-foreground ${mono ? "tabular-nums tracking-wide" : ""}`} data-testid={testId}>
      {value || value === 0 ? value : "-"}
    </span>
  </div>
);

export const SectionCard = ({ title, icon: Icon, onEdit, editLabel = "Ubah", testId, note, children }) => (
  <section className="overflow-hidden rounded-lg border border-border bg-card" data-testid={testId}>
    <div className="flex min-h-12 items-center justify-between gap-3 border-b border-border px-4 py-2">
      <h2 className="flex items-center gap-2 text-section-title">
        {Icon && <Icon className="h-4 w-4 text-muted-foreground" aria-hidden="true" />}
        {title}
      </h2>
      {onEdit && (
        <Button size="sm" variant="outline" onClick={onEdit} data-testid={`${testId}-edit-button`}>
          <Pencil className="mr-1.5 h-3.5 w-3.5" /> {editLabel}
        </Button>
      )}
    </div>
    {note && <p className="border-b border-border/60 bg-muted/30 px-4 py-2 text-[12px] text-muted-foreground">{note}</p>}
    <div className="px-4 py-1.5">{children}</div>
  </section>
);

const initials = (name) =>
  (name || "?")
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0].toUpperCase())
    .join("");

/* ------------------------------------------------------------------ foto + header */
export const EmployeeAvatar = ({ employee, size = "h-20 w-20", textSize = "text-xl" }) => {
  const [src, setSrc] = useState(null);
  useEffect(() => {
    let url = null;
    let cancelled = false;
    setSrc(null);
    if (employee?.photo_url) {
      api
        .get(employee.photo_url.replace(/^\/api/, ""), { responseType: "blob" })
        .then((res) => {
          if (cancelled) return;
          url = URL.createObjectURL(res.data);
          setSrc(url);
        })
        .catch(() => setSrc(null));
    }
    return () => {
      cancelled = true;
      if (url) URL.revokeObjectURL(url);
    };
  }, [employee?.photo_url]);
  return src ? (
    <img src={src} alt={`Foto ${employee.full_name}`} className={`${size} shrink-0 rounded-full border border-border object-cover`} data-testid="profile-photo-image" />
  ) : (
    <div
      className={`${size} ${textSize} flex shrink-0 items-center justify-center rounded-full border border-border bg-primary/10 font-semibold text-primary`}
      aria-label={`Inisial ${employee?.full_name || ""}`}
      data-testid="profile-photo-initials"
    >
      {initials(employee?.full_name)}
    </div>
  );
};

export const ProfileHeaderCard = ({ employee, canEdit, onChanged }) => {
  const input = useRef(null);
  const [busy, setBusy] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [pending, setPending] = useState(null); // file terpilih -> editor crop

  // Pilih Foto -> validasi -> buka editor posisi/crop (belum ada upload di tahap ini)
  const pick = (file) => {
    if (input.current) input.current.value = "";
    if (!file) return;
    const ext = (file.name || "").split(".").pop().toLowerCase();
    if (!PHOTO_TYPES.includes(file.type) && !["jpg", "jpeg", "png", "webp"].includes(ext)) {
      toast.error("Format foto harus JPG, PNG, atau WEBP.");
      return;
    }
    if (file.size > MAX_PHOTO_MB * 1024 * 1024) {
      toast.error(`Ukuran foto maksimal ${MAX_PHOTO_MB} MB.`);
      return;
    }
    setPending(file);
  };

  // Simpan Foto: hasil crop 1:1 diunggah; foto lama baru diganti server setelah upload baru berhasil
  const upload = async (cropped) => {
    const form = new FormData();
    form.append("file", cropped);
    setBusy(true);
    try {
      await api.post(`/employees/${employee.id}/photo`, form, { headers: { "Content-Type": "multipart/form-data" } });
      toast.success("Foto profil berhasil disimpan.");
      setPending(null);
      onChanged?.();
    } catch (err) {
      toast.error(errorMessage(err, "Foto profil gagal diunggah. Foto lama tetap dipakai."));
    } finally {
      setBusy(false);
    }
  };

  const remove = async () => {
    setBusy(true);
    try {
      await api.delete(`/employees/${employee.id}/photo`);
      toast.success("Foto profil dihapus.");
      setConfirmDelete(false);
      onChanged?.();
    } catch (err) {
      toast.error(errorMessage(err, "Foto profil gagal dihapus."));
    } finally {
      setBusy(false);
    }
  };

  const facts = [
    { icon: Briefcase, label: "Jabatan", value: employee.position_name || employee.job_title },
    { icon: Building2, label: "Divisi / Departemen", value: [employee.division_name, employee.department_name].filter(Boolean).join(" / ") },
    { icon: MapPin, label: "Project / Site", value: [employee.project_name, employee.work_location_name].filter(Boolean).join(" · ") },
  ];

  return (
    <div className="rounded-lg border border-border bg-card p-4 sm:p-5" data-testid="profile-header-card">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center">
        <div className="flex items-center gap-4">
          <EmployeeAvatar employee={employee} />
          <div className="min-w-0 sm:hidden">
            <p className="line-clamp-2 break-words text-lg font-semibold leading-snug" data-testid="profile-header-name-mobile">{employee.full_name}</p>
            <p className="text-sm text-muted-foreground">{employee.employee_number}</p>
          </div>
        </div>
        <div className="min-w-0 flex-1 space-y-2">
          <div className="hidden sm:block">
            <p className="truncate text-xl font-semibold" data-testid="profile-header-name">{employee.full_name}</p>
            <p className="text-sm text-muted-foreground" data-testid="profile-header-number">
              No. Karyawan {employee.employee_number}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2" data-testid="profile-header-status">
            <EmployeeStatusBadge
              name={employee.current_employee_status_name}
              category={employee.current_employee_status_category}
              archived={employee.status === "archived"}
              testId="profile-header-status-badge"
            />
            {employee.current_employee_status_category && (
              <span className="text-[12px] text-muted-foreground">
                Kategori: {CATEGORY_LABELS[employee.current_employee_status_category]}
              </span>
            )}
          </div>
          <dl className="grid grid-cols-1 gap-x-6 gap-y-1.5 text-[13px] sm:grid-cols-2 xl:grid-cols-3">
            {facts.map((f) => (
              <div key={f.label} className="flex min-w-0 items-start gap-2">
                <f.icon className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />
                <div className="min-w-0">
                  <dt className="text-[11px] text-muted-foreground">{f.label}</dt>
                  <dd className="break-words">{f.value || "-"}</dd>
                </div>
              </div>
            ))}
          </dl>
        </div>
        {canEdit && (
          <div className="flex flex-wrap gap-2 sm:flex-col">
            <input ref={input} type="file" accept=".jpg,.jpeg,.png,.webp,image/jpeg,image/png,image/webp" className="hidden"
              onChange={(e) => pick(e.target.files?.[0])} data-testid="profile-photo-input" />
            <Button size="sm" variant="outline" disabled={busy} onClick={() => input.current?.click()} data-testid="profile-photo-upload-button">
              {busy ? <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" /> : <Camera className="mr-1.5 h-3.5 w-3.5" />}
              {employee.photo_url ? "Ganti Foto" : "Unggah Foto"}
            </Button>
            {employee.photo_url && (
              <Button size="sm" variant="ghost" disabled={busy} onClick={() => setConfirmDelete(true)} data-testid="profile-photo-delete-button">
                <Trash2 className="mr-1.5 h-3.5 w-3.5" /> Hapus Foto
              </Button>
            )}
            <p className="text-[11px] text-muted-foreground">JPG, PNG, WEBP · maks {MAX_PHOTO_MB} MB</p>
          </div>
        )}
      </div>
      <ConfirmDialog
        open={confirmDelete}
        onOpenChange={(v) => !busy && setConfirmDelete(v)}
        title="Hapus foto profil?"
        description="Foto profil karyawan akan dihapus dan diganti avatar inisial."
        confirmLabel="Ya, hapus foto"
        loading={busy}
        onConfirm={remove}
      />
      {canEdit && (
        <PhotoCropDialog
          file={pending}
          open={!!pending}
          onOpenChange={(v) => !v && !busy && setPending(null)}
          onSave={upload}
          saving={busy}
        />
      )}
    </div>
  );
};

/* ------------------------------------------------------------------ ringkasan */
const SummaryTile = ({ icon: Icon, label, children, testId }) => (
  <div className="rounded-lg border border-border bg-card p-4" data-testid={testId}>
    <p className="mb-2 flex items-center gap-2 text-[12px] font-medium text-muted-foreground">
      <Icon className="h-4 w-4" aria-hidden="true" /> {label}
    </p>
    <div className="space-y-1 text-[13px]">{children}</div>
  </div>
);

export const SummaryTab = ({ employee, documents = [], contracts = [] }) => {
  const docStats = useMemo(() => {
    const s = { total: documents.length, expired: 0, expiring: 0 };
    documents.forEach((d) => {
      if (d.state === "expired") s.expired += 1;
      else if (d.state === "expiring") s.expiring += 1;
    });
    return s;
  }, [documents]);
  const c = employee.active_contract;
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4" data-testid="profile-summary">
      <SummaryTile icon={ShieldCheck} label="Status Karyawan" testId="summary-employee-status">
        <EmployeeStatusBadge name={employee.current_employee_status_name} category={employee.current_employee_status_category}
          archived={employee.status === "archived"} testId="summary-status-badge" />
        <p className="text-[12px] text-muted-foreground">Diubah hanya lewat aksi "Ubah Status".</p>
      </SummaryTile>
      <SummaryTile icon={Briefcase} label="Status Hubungan Kerja" testId="summary-employment-status">
        <p className="font-medium">{employee.employment_status_name || "-"}</p>
        <p className="text-[12px] text-muted-foreground">
          {c ? `${c.contract_type_name || "Kontrak"} · ${c.end_date ? `s.d. ${formatDate(c.end_date)}` : "tanpa batas waktu"}` : "Belum ada kontrak aktif"}
        </p>
      </SummaryTile>
      <SummaryTile icon={MapPin} label="Project / Site" testId="summary-project">
        <p className="font-medium">{employee.project_name || (employee.current_assignment ? "-" : "Belum ada penempatan aktif")}</p>
        <p className="text-[12px] text-muted-foreground">{employee.work_location_name || "Lokasi kerja belum diatur"}</p>
        {employee.current_assignment && (
          <p className="text-[12px] text-muted-foreground" data-testid="summary-assignment-start">
            Mulai: {employee.current_assignment.start_date ? formatDate(employee.current_assignment.start_date) : "tidak diketahui (data lama)"}
          </p>
        )}
      </SummaryTile>
      <SummaryTile icon={UserRound} label="Posisi" testId="summary-position">
        <p className="font-medium">{employee.position_name || employee.job_title || "-"}</p>
        <p className="text-[12px] text-muted-foreground">{employee.job_grade_name || "Grade belum diatur"}</p>
      </SummaryTile>
      <SummaryTile icon={CalendarDays} label="Tanggal Bergabung" testId="summary-join-date">
        <p className="font-medium">{employee.join_date ? formatDate(employee.join_date) : "-"}</p>
      </SummaryTile>
      <SummaryTile icon={Phone} label="Kontak" testId="summary-contact">
        <p className="break-words font-medium">{employee.phone || "-"}</p>
        <p className="break-words text-[12px] text-muted-foreground">{employee.email || "Email belum diisi"}</p>
      </SummaryTile>
      <SummaryTile icon={FileText} label="Dokumen" testId="summary-documents">
        <p className="font-medium">{docStats.total} dokumen tercatat</p>
        <div className="flex flex-wrap gap-1.5">
          {docStats.expired > 0 && <Badge variant="outline" className="border-destructive/40 text-destructive">{docStats.expired} kedaluwarsa</Badge>}
          {docStats.expiring > 0 && <Badge variant="outline" className="border-amber-500/40 text-amber-700 dark:text-amber-400">{docStats.expiring} segera berakhir</Badge>}
          {docStats.total > 0 && docStats.expired + docStats.expiring === 0 && <span className="text-[12px] text-muted-foreground">Semua masih berlaku</span>}
        </div>
      </SummaryTile>
      <SummaryTile icon={FileText} label="Kontrak" testId="summary-contracts">
        <p className="font-medium">{contracts.length} kontrak tercatat</p>
        <p className="text-[12px] text-muted-foreground">{c?.contract_number || (c ? "Kontrak aktif tanpa nomor" : "-")}</p>
      </SummaryTile>
    </div>
  );
};

/* ------------------------------------------------------------------ edit per bagian */
export const sectionFields = (section, catalog) => {
  const opt = (key) => (catalog?.[key] || []).map((o) => ({ value: o.id, label: o.name }));
  const enumOpt = (key) => (catalog?.[key] || []).map((o) => ({ value: o.key, label: o.label }));
  switch (section) {
    case "personal":
      return [
        { name: "full_name", label: "Nama Lengkap", required: true, colSpan: 2 },
        { name: "nik", label: "NIK KTP" },
        { name: "gender", label: "Jenis Kelamin", type: "select", options: enumOpt("genders") },
        { name: "birth_place", label: "Tempat Lahir" },
        { name: "birth_date", label: "Tanggal Lahir", type: "date" },
        { name: "marital_status", label: "Status Pernikahan", type: "select", options: enumOpt("marital_statuses") },
        { name: "religion", label: "Agama", type: "select", options: enumOpt("religions") },
        { name: "education", label: "Pendidikan Terakhir", type: "select", options: enumOpt("educations") },
        { name: "phone", label: "Nomor HP" },
        { name: "email", label: "Email Pribadi" },
        { name: "address", label: "Alamat KTP", type: "textarea", colSpan: 2 },
        { name: "domicile_address", label: "Alamat Domisili", type: "textarea", colSpan: 2 },
        { name: "city", label: "Kota / Kabupaten" },
        { name: "province", label: "Provinsi" },
        { name: "postal_code", label: "Kode Pos" },
        { name: "emergency_contact_name", label: "Kontak Darurat" },
        { name: "emergency_contact_phone", label: "Telepon Darurat" },
      ];
    case "employment":
      return [
        { name: "join_date", label: "Tanggal Bergabung", type: "date" },
        { name: "employment_status_id", label: "Status Hubungan Kerja", type: "select", options: opt("employment_statuses") },
        { name: "job_title", label: "Jabatan (teks)" },
        { name: "position_id", label: "Posisi", type: "select", options: opt("positions") },
        { name: "branch_id", label: "Cabang", type: "select", options: opt("branches") },
        { name: "work_location_id", label: "Lokasi Kerja / Site", type: "select", options: opt("work_locations") },
        { name: "department_id", label: "Departemen", type: "select", options: opt("departments") },
        { name: "division_id", label: "Divisi", type: "select", options: opt("divisions") },
        { name: "job_grade_id", label: "Grade / Level", type: "select", options: opt("job_grades") },
        { name: "cost_center_id", label: "Cost Center", type: "select", options: opt("cost_centers") },
        { name: "project_id", label: "Project", type: "select", options: opt("projects"), disabled: true,
          hint: "Ubah project lewat tab Penempatan (Tetapkan / Pindah / Akhiri) agar riwayat tercatat." },
      ];
    case "bank_tax":
      return [
        { name: "bank_name", label: "Nama Bank" },
        { name: "bank_account_number", label: "Nomor Rekening" },
        { name: "bank_account_name", label: "Nama Pemilik Rekening", colSpan: 2 },
        { name: "npwp", label: "NPWP" },
      ];
    case "bpjs":
      return [
        { name: "bpjs_kesehatan_number", label: "Nomor BPJS Kesehatan" },
        { name: "bpjs_tk_number", label: "Nomor BPJS Ketenagakerjaan (KPJ)" },
      ];
    default:
      return [];
  }
};

const SECTION_TITLES = {
  personal: "Edit Data Pribadi",
  employment: "Edit Kepegawaian",
  bank_tax: "Edit Bank & Pajak",
  bpjs: "Edit BPJS",
};

export const SectionEditDialog = ({ section, employee, catalog, onOpenChange, onSaved }) => {
  const fields = useMemo(() => sectionFields(section, catalog), [section, catalog]);
  const [values, setValues] = useState({});
  const [errors, setErrors] = useState({});
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!section) return;
    const next = {};
    fields.forEach((f) => {
      next[f.name] = employee?.[f.name] ?? "";
    });
    setValues(next);
    setErrors({});
  }, [section, fields, employee]);

  const submit = async () => {
    if (section === "personal" && (values.full_name || "").trim().length < 2) {
      setErrors({ full_name: "Nama lengkap wajib diisi (minimal 2 karakter)." });
      return;
    }
    const payload = {};
    fields.forEach((f) => {
      const v = typeof values[f.name] === "string" ? values[f.name].trim() : values[f.name];
      const cur = employee?.[f.name] ?? "";
      if ((v ?? "") !== (cur ?? "")) payload[f.name] = v === "" ? null : v;
    });
    if (Object.keys(payload).length === 0) {
      toast.info("Tidak ada perubahan untuk disimpan.");
      onOpenChange(false);
      return;
    }
    setSaving(true);
    try {
      await api.put(`/employees/${employee.id}`, payload, { params: { section } });
      toast.success("Perubahan profil disimpan.", { description: "Perubahan tercatat di audit log." });
      onOpenChange(false);
      onSaved?.();
    } catch (err) {
      const msg = errorMessage(err, "Perubahan gagal disimpan.");
      setErrors({ __form__: msg });
      toast.error(msg);
    } finally {
      setSaving(false);
    }
  };

  return (
    <FormDialog
      open={!!section}
      onOpenChange={onOpenChange}
      title={SECTION_TITLES[section] || "Edit"}
      description={`${employee?.full_name || ""}. Status Karyawan tidak diubah di sini (gunakan "Ubah Status").`}
      fields={fields}
      values={values}
      errors={errors}
      onChange={(name, value) => {
        setValues((p) => ({ ...p, [name]: value }));
        setErrors((p) => ({ ...p, [name]: undefined, __form__: undefined }));
      }}
      onSubmit={submit}
      submitting={saving}
      submitLabel="Simpan Perubahan"
    />
  );
};

/* ------------------------------------------------------------------ tab data */
export const PersonalTab = ({ employee, catalog, onEdit }) => (
  <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
    <SectionCard title="Identitas" icon={UserRound} onEdit={onEdit} editLabel="Edit Data Pribadi" testId="personal-identity-card">
      <InfoRow label="Nama Lengkap" value={employee.full_name} testId="personal-full-name" />
      <InfoRow label="Nomor Karyawan" value={employee.employee_number} testId="personal-employee-number" />
      <InfoRow label="NIK KTP" value={employee.nik} testId="personal-nik" mono />
      <InfoRow label="Tempat Lahir" value={employee.birth_place} />
      <InfoRow label="Tanggal Lahir" value={employee.birth_date ? formatDate(employee.birth_date) : null} />
      <InfoRow label="Jenis Kelamin" value={lbl(catalog?.genders, employee.gender)} />
      <InfoRow label="Status Pernikahan" value={lbl(catalog?.marital_statuses, employee.marital_status)} />
      <InfoRow label="Agama" value={lbl(catalog?.religions, employee.religion)} />
      <InfoRow label="Pendidikan Terakhir" value={lbl(catalog?.educations, employee.education)} />
    </SectionCard>
    <SectionCard title="Kontak & Alamat" icon={MapPin} testId="personal-contact-card">
      <InfoRow label="Nomor HP" value={employee.phone} testId="personal-phone" />
      <InfoRow label="Email Pribadi" value={employee.email} />
      <InfoRow label="Alamat KTP" value={employee.address} />
      <InfoRow label="Alamat Domisili" value={employee.domicile_address} testId="personal-domicile" />
      <InfoRow label="Kota / Kabupaten" value={employee.city} />
      <InfoRow label="Provinsi" value={employee.province} testId="personal-province" />
      <InfoRow label="Kode Pos" value={employee.postal_code} testId="personal-postal-code" />
      <InfoRow label="Kontak Darurat" value={employee.emergency_contact_name} />
      <InfoRow label="Telepon Darurat" value={employee.emergency_contact_phone} />
    </SectionCard>
  </div>
);

export const EmploymentTab = ({ employee, company, onEdit }) => (
  <div className="grid grid-cols-1 items-start gap-4 xl:grid-cols-2">
    <SectionCard title="Hubungan Kerja" icon={Briefcase} onEdit={onEdit} editLabel="Edit Kepegawaian" testId="employment-card">
      <InfoRow label="Nomor Karyawan" value={employee.employee_number} testId="employment-employee-number" />
      <InfoRow label="Tanggal Bergabung" value={employee.join_date ? formatDate(employee.join_date) : null} />
      <InfoRow label="Status Hubungan Kerja" value={employee.employment_status_name} testId="employment-status-name" />
      <InfoRow label="Perusahaan" value={company?.name} />
      <InfoRow
        label="Atasan / Supervisor"
        value={
          employee.supervisor_name
            ? `${employee.supervisor_name}${employee.supervisor_position_name ? ` (${employee.supervisor_position_name})` : ""}`
            : employee.supervisor_position_name
        }
        testId="employment-supervisor"
      />
    </SectionCard>
    <SectionCard title="Status Karyawan" icon={ShieldCheck} testId="employment-business-status-card"
      note="Status Karyawan (Upgrade 01B) terpisah dari Status Hubungan Kerja dan hanya dapat diubah melalui aksi Ubah Status.">
      <div className="py-2">
        <EmployeeStatusBadge name={employee.current_employee_status_name} category={employee.current_employee_status_category}
          archived={employee.status === "archived"} testId="employment-business-status-badge" />
      </div>
    </SectionCard>
    <SectionCard title="Organisasi" icon={Building2} testId="employment-org-card">
      <InfoRow label="Cabang" value={employee.branch_name} />
      <InfoRow label="Lokasi Kerja" value={employee.work_location_name} />
      <InfoRow label="Departemen" value={employee.department_name} />
      <InfoRow label="Divisi" value={employee.division_name} />
      <InfoRow label="Posisi" value={employee.position_name} />
      <InfoRow label="Jabatan (teks)" value={employee.job_title} />
      <InfoRow label="Grade / Level" value={employee.job_grade_name} />
      <InfoRow label="Cost Center" value={employee.cost_center_name} />
    </SectionCard>
  </div>
);

const MaskedNote = ({ masked }) =>
  masked ? "Sebagian data disamarkan karena Anda tidak memiliki hak ubah data karyawan." : undefined;

export const BankTaxTab = ({ employee, onEdit, salaryInfo, payrollVisible }) => (
  <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
    <SectionCard title="Rekening Bank" icon={Building2} onEdit={onEdit} editLabel="Edit Bank & Pajak" testId="bank-card"
      note={MaskedNote({ masked: employee.sensitive_masked })}>
      <InfoRow label="Nama Bank" value={employee.bank_name} />
      <InfoRow label="Nomor Rekening" value={employee.bank_account_number} testId="bank-account-number" mono />
      <InfoRow label="Nama Pemilik Rekening" value={employee.bank_account_name} />
    </SectionCard>
    <SectionCard title="Pajak" icon={FileText} testId="tax-card"
      note="Status PTKP dikelola di modul Payroll (Gaji Karyawan). Perhitungan PPh 21 tetap memakai engine payroll existing.">
      <InfoRow label="NPWP" value={employee.npwp} testId="tax-npwp" mono />
      <InfoRow label="Status PTKP" value={payrollVisible ? salaryInfo?.salary?.ptkp_status : null} testId="tax-ptkp" />
    </SectionCard>
  </div>
);

export const BpjsTab = ({ employee, onEdit }) => (
  <SectionCard title="BPJS" icon={ShieldCheck} onEdit={onEdit} editLabel="Edit BPJS" testId="bpjs-card"
    note={MaskedNote({ masked: employee.sensitive_masked }) || "Data kepesertaan saja. Perhitungan iuran BPJS tetap di modul Payroll."}>
    <InfoRow label="Nomor BPJS Kesehatan" value={employee.bpjs_kesehatan_number} testId="bpjs-kesehatan" mono />
    <InfoRow label="Nomor BPJS Ketenagakerjaan (KPJ)" value={employee.bpjs_tk_number} testId="bpjs-tk" mono />
  </SectionCard>
);

/* ------------------------------------------------------------------ keluarga */
const FAMILY_EMPTY = { relationship: "", full_name: "", nik: "", birth_place: "", birth_date: "", gender: "",
  occupation: "", is_emergency_contact: false, phone: "", notes: "" };

export const FamilyTab = ({ employeeId, canEdit, catalog }) => {
  const [state, setState] = useState({ loading: true, error: null, items: [], relationships: [], masked: false });
  const [dialog, setDialog] = useState(null);
  const [values, setValues] = useState(FAMILY_EMPTY);
  const [errors, setErrors] = useState({});
  const [saving, setSaving] = useState(false);
  const [toDelete, setToDelete] = useState(null);

  const load = useCallback(async () => {
    setState((s) => ({ ...s, loading: true, error: null }));
    try {
      const res = await api.get(`/employees/${employeeId}/family`);
      setState({ loading: false, error: null, items: res.data.items, relationships: res.data.relationships, masked: res.data.sensitive_masked });
    } catch (err) {
      setState((s) => ({ ...s, loading: false, error: errorMessage(err, "Data keluarga gagal dimuat.") }));
    }
  }, [employeeId]);
  useEffect(() => { load(); }, [load]);

  const fields = useMemo(() => [
    { name: "relationship", label: "Hubungan", type: "select", required: true, options: state.relationships },
    { name: "full_name", label: "Nama", required: true },
    { name: "nik", label: "NIK", hint: "Opsional, 16 digit." },
    { name: "gender", label: "Jenis Kelamin", type: "select", options: (catalog?.genders || []).map((g) => ({ value: g.key, label: g.label })) },
    { name: "birth_place", label: "Tempat Lahir" },
    { name: "birth_date", label: "Tanggal Lahir", type: "date" },
    { name: "occupation", label: "Pekerjaan" },
    { name: "phone", label: "Nomor HP" },
    { name: "is_emergency_contact", label: "Kontak Darurat", type: "boolean" },
    { name: "notes", label: "Catatan", type: "textarea", colSpan: 2 },
  ], [state.relationships, catalog]);

  const open = (row) => {
    setValues(row ? { ...FAMILY_EMPTY, ...Object.fromEntries(Object.entries(row).map(([k, v]) => [k, v ?? ""])), is_emergency_contact: !!row.is_emergency_contact } : FAMILY_EMPTY);
    setErrors({});
    setDialog({ mode: row ? "edit" : "create", row });
  };

  const submit = async () => {
    const e = {};
    if (!values.relationship) e.relationship = "Hubungan wajib dipilih.";
    if ((values.full_name || "").trim().length < 2) e.full_name = "Nama wajib diisi.";
    if (values.nik && !/^\d{16}$/.test(values.nik)) e.nik = "NIK harus 16 digit angka.";
    if (values.birth_date && values.birth_date > new Date().toISOString().slice(0, 10)) e.birth_date = "Tanggal lahir tidak boleh di masa depan.";
    if (Object.keys(e).length) { setErrors(e); return; }
    const payload = Object.fromEntries(
      Object.keys(FAMILY_EMPTY).map((k) => [k, typeof values[k] === "string" ? values[k].trim() || null : values[k]])
    );
    payload.full_name = values.full_name.trim();
    setSaving(true);
    try {
      if (dialog.mode === "edit") await api.put(`/employees/${employeeId}/family/${dialog.row.id}`, payload);
      else await api.post(`/employees/${employeeId}/family`, payload);
      toast.success(dialog.mode === "edit" ? "Data keluarga diperbarui." : "Anggota keluarga ditambahkan.");
      setDialog(null);
      load();
    } catch (err) {
      setErrors({ __form__: errorMessage(err, "Data keluarga gagal disimpan.") });
    } finally {
      setSaving(false);
    }
  };

  const doDelete = async () => {
    setSaving(true);
    try {
      await api.delete(`/employees/${employeeId}/family/${toDelete.id}`);
      toast.success("Data keluarga dihapus.");
      setToDelete(null);
      load();
    } catch (err) {
      toast.error(errorMessage(err, "Data keluarga gagal dihapus."));
    } finally {
      setSaving(false);
    }
  };

  return (
    <SectionCard title="Keluarga" icon={Users} testId="family-card"
      note={state.masked ? "NIK anggota keluarga disamarkan karena Anda tidak memiliki hak ubah data karyawan." : undefined}>
      <div className="flex items-center justify-between gap-2 py-2">
        <p className="text-[12px] text-muted-foreground" data-testid="family-count">{state.items.length} anggota keluarga</p>
        {canEdit && (
          <Button size="sm" onClick={() => open(null)} data-testid="family-add-button">
            <Plus className="mr-1.5 h-3.5 w-3.5" /> Tambah Keluarga
          </Button>
        )}
      </div>
      {state.loading ? (
        <div className="space-y-2 py-2"><Skeleton className="h-12 w-full" /><Skeleton className="h-12 w-full" /></div>
      ) : state.error ? (
        <div className="flex items-center justify-between gap-2 py-3 text-sm text-destructive" data-testid="family-error">
          {state.error}
          <Button size="sm" variant="outline" onClick={load} data-testid="family-retry-button">Coba lagi</Button>
        </div>
      ) : state.items.length === 0 ? (
        <p className="py-6 text-center text-sm text-muted-foreground" data-testid="family-empty">
          Belum ada data keluarga. {canEdit ? "Tambahkan anggota keluarga untuk melengkapi profil." : ""}
        </p>
      ) : (
        <ul className="divide-y divide-border/60" data-testid="family-list">
          {state.items.map((m) => (
            <li key={m.id} className="flex flex-col gap-2 py-3 sm:flex-row sm:items-start sm:justify-between" data-testid={`family-row-${m.id}`}>
              <div className="min-w-0 space-y-0.5">
                <div className="flex flex-wrap items-center gap-2 font-medium">
                  <span data-testid={`family-name-${m.id}`}>{m.full_name}</span>
                  <Badge variant="secondary">{m.relationship_label}</Badge>
                  {m.is_emergency_contact && <Badge variant="outline" data-testid={`family-emergency-${m.id}`}>Kontak Darurat</Badge>}
                </div>
                <p className="text-[12px] text-muted-foreground">
                  {[m.birth_place, m.birth_date ? formatDate(m.birth_date) : null].filter(Boolean).join(", ") || "Tanggal lahir belum diisi"}
                  {m.occupation ? ` · ${m.occupation}` : ""}{m.phone ? ` · ${m.phone}` : ""}
                </p>
                {m.nik && <p className="text-[12px] tabular-nums tracking-wide text-muted-foreground" data-testid={`family-nik-${m.id}`}>NIK {m.nik}</p>}
                {m.notes && <p className="break-words text-[12px] text-muted-foreground">{m.notes}</p>}
              </div>
              {canEdit && (
                <div className="flex shrink-0 gap-1">
                  <Button size="sm" variant="ghost" onClick={() => open(m)} data-testid={`family-edit-${m.id}`}><Pencil className="mr-1 h-3.5 w-3.5" /> Ubah</Button>
                  <Button size="sm" variant="ghost" className="text-destructive" onClick={() => setToDelete(m)} data-testid={`family-delete-${m.id}`}><Trash2 className="mr-1 h-3.5 w-3.5" /> Hapus</Button>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
      <FormDialog
        open={!!dialog}
        onOpenChange={(v) => !v && setDialog(null)}
        title={dialog?.mode === "edit" ? "Ubah Data Keluarga" : "Tambah Anggota Keluarga"}
        description="Data keluarga tercatat di audit log."
        fields={fields}
        values={values}
        errors={errors}
        onChange={(name, value) => { setValues((p) => ({ ...p, [name]: value })); setErrors((p) => ({ ...p, [name]: undefined, __form__: undefined })); }}
        onSubmit={submit}
        submitting={saving}
        submitLabel="Simpan"
      />
      <ConfirmDialog
        open={!!toDelete}
        onOpenChange={(v) => !saving && !v && setToDelete(null)}
        title="Hapus anggota keluarga?"
        description={`${toDelete?.full_name || ""} akan dihapus dari data keluarga karyawan.`}
        confirmLabel="Ya, hapus"
        loading={saving}
        onConfirm={doDelete}
      />
    </SectionCard>
  );
};

/* ------------------------------------------------------------------ riwayat */
const ACTION_LABELS = {
  create: "Dibuat", update: "Diubah", delete: "Dihapus", approve: "Disetujui", renew: "Diperpanjang",
  status_change: "Status karyawan diubah", family_create: "Keluarga ditambah", family_update: "Keluarga diubah",
  family_delete: "Keluarga dihapus", photo_upload: "Foto profil diunggah", photo_replace: "Foto profil diganti",
  photo_delete: "Foto profil dihapus", assignment_create: "Penempatan ditetapkan", assignment_transfer: "Pindah penempatan", assignment_end: "Penempatan diakhiri", archive: "Diarsipkan", restore: "Dipulihkan", upload: "Diunggah",
};
const RESOURCE_LABELS = { employee: "Karyawan", contract: "Kontrak", certification: "Sertifikasi", document: "Dokumen" };

export const HistoryTab = ({ employeeId, refreshKey }) => {
  const [state, setState] = useState({ loading: true, error: null, items: [] });
  const load = useCallback(async () => {
    setState((s) => ({ ...s, loading: true, error: null }));
    try {
      const res = await api.get(`/employees/${employeeId}/timeline`);
      setState({ loading: false, error: null, items: res.data.items });
    } catch (err) {
      setState({ loading: false, error: errorMessage(err, "Riwayat aktivitas gagal dimuat."), items: [] });
    }
  }, [employeeId]);
  useEffect(() => { load(); }, [load, refreshKey]);
  return (
    <div className="space-y-4">
      <StatusHistoryCard employeeId={employeeId} refreshKey={refreshKey} />
      <SectionCard title="Aktivitas Profil" icon={History} testId="timeline-card"
        note="Diambil dari audit log (kontrak, sertifikasi, dokumen, dan perubahan data karyawan). Tidak ada riwayat yang dibuat dari data saat ini.">
        {state.loading ? (
          <div className="space-y-2 py-2"><Skeleton className="h-10 w-full" /><Skeleton className="h-10 w-full" /></div>
        ) : state.error ? (
          <div className="flex items-center justify-between gap-2 py-3 text-sm text-destructive" data-testid="timeline-error">
            {state.error}<Button size="sm" variant="outline" onClick={load} data-testid="timeline-retry-button">Coba lagi</Button>
          </div>
        ) : state.items.length === 0 ? (
          <p className="py-6 text-center text-sm text-muted-foreground" data-testid="timeline-empty">Belum ada aktivitas tercatat.</p>
        ) : (
          <ol className="divide-y divide-border/60" data-testid="timeline-list">
            {state.items.map((a) => (
              <li key={a.id} className="flex flex-col gap-0.5 py-2.5 sm:flex-row sm:items-center sm:justify-between" data-testid={`timeline-item-${a.id}`}>
                <div className="min-w-0">
                  <p className="text-[13px] font-medium">
                    {RESOURCE_LABELS[a.resource] || a.resource}: {a.notes || ACTION_LABELS[a.action] || a.action}
                  </p>
                  <p className="truncate text-[12px] text-muted-foreground">
                    {a.record_label || "-"}{a.changed_fields?.length && (a.action === "update" || a.action?.endsWith("_update")) ? ` · ${a.changed_fields.length} field berubah` : ""}
                  </p>
                </div>
                <p className="shrink-0 text-[12px] text-muted-foreground">
                  {a.user_name || "Sistem"} · {a.created_at ? new Date(a.created_at).toLocaleString("id-ID", { dateStyle: "medium", timeStyle: "short" }) : "-"}
                </p>
              </li>
            ))}
          </ol>
        )}
      </SectionCard>
    </div>
  );
};
