import React, { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  ArrowLeft,
  ClipboardCheck,
  Eye,
  FileText,
  History,
  Loader2,
  Pencil,
  PlayCircle,
  Trash2,
  Upload,
  UserRound,
  UserRoundPlus,
} from "lucide-react";
import { toast } from "sonner";
import { api, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { formatCurrency, formatDate, formatDateTime, formatFileSize } from "@/lib/format";
import { HISTORY_ACTION_LABELS, RECRUITMENT_ROUTES, toCandidatePayload } from "@/lib/recruitment";
import PageHeader, { PageBody } from "@/components/common/PageHeader";
import DataTable, { TableCard } from "@/components/common/DataTable";
import ConfirmDialog from "@/components/common/ConfirmDialog";
import EmptyState from "@/components/common/EmptyState";
import DocumentPreviewDialog from "@/components/common/DocumentPreview";
import StageBadge from "@/components/recruitment/StageBadge";
import CandidateFormDialog from "@/components/recruitment/CandidateFormDialog";
import ScreeningDialog from "@/components/recruitment/ScreeningDialog";
import InterviewTab from "@/components/recruitment/InterviewTab";
import ApprovalTab from "@/components/recruitment/ApprovalTab";
import OfferingTab from "@/components/recruitment/OfferingTab";
import ConvertEmployeeDialog, { HiredPanel } from "@/components/recruitment/ConvertEmployeeDialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

const InfoRow = ({ label, value, testId }) => (
  <div className="grid grid-cols-1 gap-0.5 border-b border-border/60 py-1.5 last:border-0 sm:grid-cols-[11rem,1fr] sm:gap-4">
    <span className="text-[12px] text-muted-foreground">{label}</span>
    <span className="text-[13px] text-foreground" data-testid={testId}>
      {value || "-"}
    </span>
  </div>
);

const InfoCard = ({ title, children }) => (
  <div className="overflow-hidden rounded-lg border border-border bg-card">
    <div className="border-b border-border px-4 py-2.5">
      <h2 className="text-section-title">{title}</h2>
    </div>
    <div className="px-4 py-2">{children}</div>
  </div>
);

const labelOf = (list, key) => (list || []).find((x) => x.key === key)?.label || key || "";

const EDIT_FIELDS = [
  "full_name", "candidate_number", "nik", "gender", "birth_place", "birth_date", "phone", "email", "city", "address",
  "position_id", "applied_position_title", "department_id", "work_location_id", "project_id", "source", "source_detail",
  "applied_at", "expected_salary", "available_from", "last_education", "major", "institution", "graduation_year",
  "last_company", "last_position", "experience_years", "notes",
];

const CandidateDetailPage = () => {
  const { candidateId } = useParams();
  const navigate = useNavigate();
  const { can, hasModule } = useAuth();

  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [pipeline, setPipeline] = useState(null);
  const [pipelineLoading, setPipelineLoading] = useState(true);
  const [pipelineError, setPipelineError] = useState("");
  const [interviewers, setInterviewers] = useState([]);
  const [catalog, setCatalog] = useState(null);
  const [documents, setDocuments] = useState([]);
  const [docTypes, setDocTypes] = useState([]);
  const [docsLoading, setDocsLoading] = useState(false);

  const [editOpen, setEditOpen] = useState(false);
  const [values, setValues] = useState({});
  const [errors, setErrors] = useState({});
  const [submitting, setSubmitting] = useState(false);

  const [screeningOpen, setScreeningOpen] = useState(false);
  const [convertOpen, setConvertOpen] = useState(false);
  const [confirm, setConfirm] = useState(null); // {kind:'start'|'delete'|'document', row?}
  const [confirmLoading, setConfirmLoading] = useState(false);
  const [previewId, setPreviewId] = useState(null);

  const [uploadOpen, setUploadOpen] = useState(false);
  const [uploadForm, setUploadForm] = useState({ document_type_id: "", name: "", expiry_date: "" });
  const [uploadFile, setUploadFile] = useState(null);
  const [uploadError, setUploadError] = useState("");
  const [uploading, setUploading] = useState(false);
  const fileInput = useRef(null);

  const candidate = data?.candidate;

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.get(`/recruitment/candidates/${candidateId}`);
      setData(res.data);
      document.title = `${res.data.candidate.full_name} · Kandidat`;
    } catch (err) {
      toast.error(errorMessage(err, "Data kandidat tidak dapat dimuat."));
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [candidateId]);

  const loadPipeline = useCallback(async () => {
    setPipelineLoading(true);
    setPipelineError("");
    try {
      const res = await api.get(`/recruitment/candidates/${candidateId}/pipeline`);
      setPipeline(res.data);
    } catch (err) {
      setPipelineError(errorMessage(err, "Data interview / approval / offering tidak dapat dimuat."));
    } finally {
      setPipelineLoading(false);
    }
  }, [candidateId]);

  /** Muat ulang kandidat + pipeline setelah aksi Tahap B (interview/approval/offering). */
  const reloadAll = useCallback(() => {
    load();
    loadPipeline();
  }, [load, loadPipeline]);

  const loadDocuments = useCallback(async () => {
    if (!can("document", "view")) return;
    setDocsLoading(true);
    try {
      const res = await api.get("/documents", {
        params: { owner_type: "applicant", owner_id: candidateId, limit: 100 },
      });
      setDocuments(res.data.items || []);
    } catch (err) {
      /* dokumen bersifat pelengkap */
    } finally {
      setDocsLoading(false);
    }
  }, [candidateId, can]);

  const loadSide = useCallback(async () => {
    try {
      const [cat, docCat, interviewerRes] = await Promise.all([
        api.get("/recruitment/catalog"),
        can("document", "view") ? api.get("/documents/catalog") : Promise.resolve({ data: { document_types: [] } }),
        api.get("/recruitment/interviewers").catch(() => ({ data: { items: [] } })),
      ]);
      setCatalog(cat.data);
      setDocTypes(docCat.data.document_types || []);
      setInterviewers(interviewerRes.data.items || []);
    } catch (err) {
      /* pelengkap */
    }
  }, [can]);

  useEffect(() => {
    load();
    loadPipeline();
    loadDocuments();
    loadSide();
  }, [load, loadPipeline, loadDocuments, loadSide]);

  const openEdit = () => {
    const v = {};
    EDIT_FIELDS.forEach((k) => {
      v[k] = candidate?.[k] ?? "";
    });
    setValues(v);
    setErrors({});
    setEditOpen(true);
  };

  const submitEdit = async () => {
    if (!values.full_name || values.full_name.trim().length < 2) {
      setErrors({ full_name: "Nama lengkap wajib diisi (minimal 2 karakter)." });
      return;
    }
    setSubmitting(true);
    setErrors({});
    try {
      await api.put(`/recruitment/candidates/${candidateId}`, toCandidatePayload(values));
      toast.success("Data kandidat berhasil diperbarui.");
      setEditOpen(false);
      load();
    } catch (err) {
      setErrors({ __form__: errorMessage(err, "Data kandidat tidak dapat disimpan.") });
    } finally {
      setSubmitting(false);
    }
  };

  const runConfirm = async () => {
    setConfirmLoading(true);
    try {
      if (confirm.kind === "start") {
        await api.post(`/recruitment/candidates/${candidateId}/status`, {
          stage_status: "screening",
          notes: "Screening dimulai oleh HR",
        });
        toast.success("Screening dimulai. Isi hasil screening pada tab Screening.");
        reloadAll();
      } else if (confirm.kind === "delete") {
        const res = await api.delete(`/recruitment/candidates/${candidateId}`);
        toast.success(res.data.message);
        navigate(RECRUITMENT_ROUTES.candidates, { replace: true });
        return;
      } else if (confirm.kind === "document") {
        const res = await api.delete(`/documents/${confirm.row.id}`);
        toast.success(res.data.message || "Dokumen dihapus.");
        loadDocuments();
        load();
      }
      setConfirm(null);
    } catch (err) {
      toast.error(errorMessage(err, "Tindakan tidak dapat diselesaikan."));
      setConfirm(null);
    } finally {
      setConfirmLoading(false);
    }
  };

  const submitUpload = async () => {
    setUploadError("");
    if (!uploadFile) return setUploadError("Pilih berkas yang ingin diunggah terlebih dahulu.");
    if (!uploadForm.document_type_id) return setUploadError("Tipe dokumen wajib dipilih.");
    if (!uploadForm.name?.trim()) return setUploadError("Nama dokumen wajib diisi.");
    setUploading(true);
    try {
      const fd = new FormData();
      fd.append("file", uploadFile);
      fd.append("document_type_id", uploadForm.document_type_id);
      fd.append("name", uploadForm.name);
      fd.append("owner_type", "applicant");
      fd.append("owner_id", candidateId);
      fd.append("owner_label", candidate?.full_name || "");
      if (uploadForm.expiry_date) fd.append("expiry_date", uploadForm.expiry_date);
      await api.post("/documents", fd, { headers: { "Content-Type": "multipart/form-data" } });
      toast.success(`Dokumen "${uploadForm.name}" berhasil diunggah.`);
      setUploadOpen(false);
      setUploadFile(null);
      loadDocuments();
      load();
    } catch (err) {
      setUploadError(errorMessage(err, "Dokumen tidak dapat diunggah."));
    } finally {
      setUploading(false);
    }
    return undefined;
  };

  if (loading && !data) {
    return (
      <PageBody>
        <Skeleton className="h-24 w-full" />
        <Skeleton className="h-64 w-full" />
      </PageBody>
    );
  }

  if (!candidate) {
    return (
      <PageBody>
        <div className="rounded-lg border border-border bg-card">
          <EmptyState
            icon={UserRound}
            title="Kandidat tidak ditemukan."
            description="Kandidat mungkin sudah dihapus atau bukan milik perusahaan aktif Anda."
            actionLabel="Kembali ke daftar"
            onAction={() => navigate(RECRUITMENT_ROUTES.candidates)}
          />
        </div>
      </PageBody>
    );
  }

  const stage = candidate.stage_status;
  const isHired = stage === "hired";
  const conversion = pipeline?.conversion;
  const canEdit = can("recruitment", "edit") && !isHired;
  const canStart = can("recruitment", "edit") && (candidate.allowed_next || []).includes("screening");
  const canScreen = can("recruitment", "edit") && candidate.can_screen;
  const canDelete = can("recruitment", "delete") && candidate.can_delete && !isHired;
  const canConvert =
    stage === "offering_accepted" &&
    !candidate.employee_id &&
    can("recruitment", "edit") &&
    can("employee", "create") &&
    hasModule("employee_core") &&
    (conversion ? conversion.can_convert : true);
  const docsReadOnly = isHired;

  const documentColumns = [
    {
      key: "name",
      header: "Dokumen",
      render: (row) => (
        <div className="flex min-w-0 items-start gap-2">
          <FileText className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
          <div className="min-w-0">
            <p className="truncate font-medium">{row.name}</p>
            <p className="truncate text-xs text-muted-foreground">
              {row.document_type_name || "-"} · {formatFileSize(row.file_size)}
            </p>
          </div>
        </div>
      ),
    },
    {
      key: "created_at",
      header: "Diunggah",
      hideOnMobile: true,
      render: (row) => <span className="text-sm">{formatDateTime(row.created_at)}</span>,
    },
    {
      key: "actions",
      header: "",
      className: "w-40 text-right",
      render: (row) => (
        <div className="flex items-center justify-end gap-2">
          <Button variant="outline" size="sm" onClick={() => setPreviewId(row.id)} data-testid={`candidate-doc-preview-${row.id}`}>
            <Eye className="mr-1.5 h-3.5 w-3.5" /> Pratinjau
          </Button>
          {can("document", "delete") && !docsReadOnly && (
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8 text-destructive"
              onClick={() => setConfirm({ kind: "document", row })}
              data-testid={`candidate-doc-delete-${row.id}`}
            >
              <Trash2 className="h-4 w-4" />
            </Button>
          )}
        </div>
      ),
    },
  ];

  return (
    <>
      <PageHeader
        title={candidate.full_name}
        subtitle={`${candidate.candidate_number}${
          candidate.position_name || candidate.applied_position_title
            ? ` · ${candidate.position_name || candidate.applied_position_title}`
            : ""
        }${candidate.department_name ? ` · ${candidate.department_name}` : ""}`}
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <StageBadge stage={stage} label={candidate.stage_label} tone={candidate.stage_tone} testId="candidate-detail-stage" className="self-center" />
            <Button variant="outline" onClick={() => navigate(RECRUITMENT_ROUTES.candidates)} data-testid="candidate-back-button">
              <ArrowLeft className="mr-2 h-4 w-4" /> Kembali
            </Button>
            {canEdit && (
              <Button variant="outline" onClick={openEdit} data-testid="candidate-edit-button">
                <Pencil className="mr-2 h-4 w-4" /> Ubah
              </Button>
            )}
            {canStart && (
              <Button onClick={() => setConfirm({ kind: "start" })} data-testid="candidate-start-screening">
                <PlayCircle className="mr-2 h-4 w-4" /> Mulai Screening
              </Button>
            )}
            {canScreen && (
              <Button onClick={() => setScreeningOpen(true)} data-testid="candidate-fill-screening">
                <ClipboardCheck className="mr-2 h-4 w-4" /> Isi Hasil Screening
              </Button>
            )}
            {canConvert && (
              <Button onClick={() => setConvertOpen(true)} data-testid="candidate-convert-button">
                <UserRoundPlus className="mr-2 h-4 w-4" /> Jadikan Karyawan
              </Button>
            )}
            {canDelete && (
              <Button
                variant="ghost"
                className="text-destructive hover:text-destructive"
                onClick={() => setConfirm({ kind: "delete" })}
                data-testid="candidate-delete-button"
              >
                <Trash2 className="mr-2 h-4 w-4" /> Hapus
              </Button>
            )}
          </div>
        }
      />

      <PageBody>
        {isHired && <HiredPanel conversion={conversion} loading={pipelineLoading} />}
        {stage === "offering_accepted" && !isHired && conversion && !conversion.can_convert && conversion.blockers?.length > 0 && (
          <div className="rounded-lg border border-border bg-muted/40 px-4 py-2.5 text-[12px] text-muted-foreground" data-testid="convert-blocked-note">
            Jadikan Karyawan belum tersedia: {conversion.blockers.join(" ")}
          </div>
        )}
        <Tabs defaultValue="profile">
          <TabsList data-testid="candidate-tabs" className="flex-wrap">
            <TabsTrigger value="profile" data-testid="tab-profile">Profil</TabsTrigger>
            <TabsTrigger value="application" data-testid="tab-application">Lamaran</TabsTrigger>
            <TabsTrigger value="screening" data-testid="tab-screening">Screening</TabsTrigger>
            <TabsTrigger value="interview" data-testid="tab-interview">
              Interview{pipeline ? ` (${pipeline.interviews.length})` : ""}
            </TabsTrigger>
            <TabsTrigger value="approval" data-testid="tab-approval">Approval</TabsTrigger>
            <TabsTrigger value="offering" data-testid="tab-offering">
              Offering{pipeline ? ` (${pipeline.offerings.items.length})` : ""}
            </TabsTrigger>
            <TabsTrigger value="documents" data-testid="tab-documents">Dokumen ({documents.length})</TabsTrigger>
            <TabsTrigger value="history" data-testid="tab-history">Riwayat ({data.history.length})</TabsTrigger>
          </TabsList>

          {/* ---------------- Profil ---------------- */}
          <TabsContent value="profile" className="mt-4 space-y-4">
            <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
              <InfoCard title="Identitas">
                <InfoRow label="Nama Lengkap" value={candidate.full_name} testId="detail-full-name" />
                <InfoRow label="Nomor Kandidat" value={candidate.candidate_number} testId="detail-candidate-number" />
                <InfoRow label="NIK" value={candidate.nik} testId="detail-nik" />
                <InfoRow label="Jenis Kelamin" value={labelOf(catalog?.genders, candidate.gender)} />
                <InfoRow
                  label="Tempat, Tanggal Lahir"
                  value={[candidate.birth_place, candidate.birth_date ? formatDate(candidate.birth_date) : null].filter(Boolean).join(", ")}
                />
                <InfoRow label="No. HP / WhatsApp" value={candidate.phone} testId="detail-phone" />
                <InfoRow label="Email" value={candidate.email} testId="detail-email" />
                <InfoRow label="Kota" value={candidate.city} />
                <InfoRow label="Alamat" value={candidate.address} />
              </InfoCard>
              <InfoCard title="Pendidikan & Pengalaman">
                <InfoRow label="Pendidikan Terakhir" value={labelOf(catalog?.educations, candidate.last_education)} />
                <InfoRow label="Jurusan" value={candidate.major} />
                <InfoRow label="Institusi" value={candidate.institution} />
                <InfoRow label="Tahun Lulus" value={candidate.graduation_year} />
                <InfoRow label="Perusahaan Terakhir" value={candidate.last_company} />
                <InfoRow label="Posisi Terakhir" value={candidate.last_position} />
                <InfoRow
                  label="Lama Pengalaman"
                  value={candidate.experience_years !== null && candidate.experience_years !== undefined ? `${candidate.experience_years} tahun` : null}
                />
                <InfoRow label="Catatan HR" value={candidate.notes} />
              </InfoCard>
            </div>
          </TabsContent>

          {/* ---------------- Lamaran ---------------- */}
          <TabsContent value="application" className="mt-4 space-y-4">
            <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
              <InfoCard title="Posisi yang Dilamar">
                <InfoRow label="Posisi" value={candidate.position_name || candidate.applied_position_title} testId="detail-position" />
                {candidate.position_name && candidate.applied_position_title && (
                  <InfoRow label="Sebutan Posisi" value={candidate.applied_position_title} />
                )}
                <InfoRow label="Departemen" value={candidate.department_name} testId="detail-department" />
                <InfoRow label="Lokasi Kerja" value={candidate.work_location_name} />
                <InfoRow label="Proyek" value={candidate.project_name} />
              </InfoCard>
              <InfoCard title="Informasi Lamaran">
                <InfoRow label="Sumber Kandidat" value={candidate.source_label} testId="detail-source" />
                <InfoRow label="Detail Sumber" value={candidate.source_detail} />
                <InfoRow label="Tanggal Masuk" value={candidate.applied_at ? formatDate(candidate.applied_at) : null} />
                <InfoRow
                  label="Ekspektasi Gaji"
                  value={candidate.expected_salary ? formatCurrency(candidate.expected_salary) : null}
                  testId="detail-expected-salary"
                />
                <InfoRow label="Siap Bekerja Mulai" value={candidate.available_from ? formatDate(candidate.available_from) : null} />
              </InfoCard>
            </div>
          </TabsContent>

          {/* ---------------- Screening ---------------- */}
          <TabsContent value="screening" className="mt-4 space-y-4">
            {candidate.screening_result ? (
              <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
                <InfoCard title="Hasil Screening">
                  <InfoRow
                    label="Keputusan"
                    value={
                      <StageBadge
                        stage={stage}
                        label={candidate.screening_result_label}
                        tone={candidate.screening_result === "passed" ? "success" : "danger"}
                        testId="screening-result-badge"
                      />
                    }
                  />
                  <InfoRow label="Skor" value={candidate.screening_score !== null && candidate.screening_score !== undefined ? `${candidate.screening_score} / 100` : null} testId="screening-score-value" />
                  <InfoRow label="Rekomendasi" value={candidate.screening_recommendation_label} testId="screening-recommendation-value" />
                  <InfoRow label="Diperiksa oleh" value={candidate.screened_by_name} />
                  <InfoRow label="Waktu" value={candidate.screened_at ? formatDateTime(candidate.screened_at) : null} />
                </InfoCard>
                <InfoCard title="Catatan Screening">
                  <p className="whitespace-pre-wrap py-1.5 text-[13px]" data-testid="screening-notes-value">
                    {candidate.screening_notes || "-"}
                  </p>
                </InfoCard>
              </div>
            ) : (
              <div className="rounded-lg border border-border bg-card" data-testid="screening-empty">
                <EmptyState
                  icon={ClipboardCheck}
                  title={stage === "screening" ? "Screening sedang berjalan." : "Screening belum dimulai."}
                  description={
                    stage === "screening"
                      ? "Isi skor, catatan, rekomendasi, dan keputusan lolos / tidak lolos. Status kandidat berubah otomatis."
                      : "Mulai screening untuk memindahkan kandidat dari Draft ke tahap Screening."
                  }
                  actionLabel={canScreen ? "Isi Hasil Screening" : canStart ? "Mulai Screening" : undefined}
                  onAction={canScreen ? () => setScreeningOpen(true) : canStart ? () => setConfirm({ kind: "start" }) : undefined}
                />
              </div>
            )}
          </TabsContent>

          {/* ---------------- Interview / Approval / Offering (Tahap B) ---------------- */}
          {["interview", "approval", "offering"].map((key) => (
            <TabsContent key={key} value={key} className="mt-4 space-y-4">
              {pipelineLoading && !pipeline ? (
                <div className="space-y-3" data-testid={`${key}-loading`}>
                  <Skeleton className="h-12 w-full" />
                  <Skeleton className="h-40 w-full" />
                </div>
              ) : pipelineError && !pipeline ? (
                <div className="rounded-lg border border-border bg-card" data-testid={`${key}-error`}>
                  <EmptyState
                    icon={History}
                    title="Data proses seleksi tidak dapat dimuat."
                    description={pipelineError}
                    actionLabel="Coba lagi"
                    onAction={loadPipeline}
                  />
                </div>
              ) : key === "interview" ? (
                <InterviewTab
                  candidate={pipeline.candidate}
                  interviews={pipeline.interviews}
                  interviewers={interviewers}
                  catalog={catalog}
                  canSchedule={pipeline.can_schedule_interview}
                  onChanged={reloadAll}
                />
              ) : key === "approval" ? (
                <ApprovalTab candidate={pipeline.candidate} approval={pipeline.approval} onChanged={reloadAll} />
              ) : (
                <OfferingTab candidate={pipeline.candidate} offerings={pipeline.offerings} catalog={catalog} onChanged={reloadAll} />
              )}
            </TabsContent>
          ))}

          {/* ---------------- Dokumen ---------------- */}
          <TabsContent value="documents" className="mt-4 space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="text-sm text-muted-foreground">
                CV, KTP, ijazah, sertifikat, dan dokumen pendukung kandidat. Tersimpan di modul Dokumen (pemilik: Pelamar).
                {docsReadOnly ? " Kandidat sudah menjadi karyawan — dokumen bersifat read-only." : ""}
              </p>
              {can("document", "create") && !docsReadOnly && (
                <Button
                  onClick={() => {
                    setUploadForm({ document_type_id: docTypes[0]?.id || "", name: "", expiry_date: "" });
                    setUploadFile(null);
                    setUploadError("");
                    setUploadOpen(true);
                  }}
                  data-testid="candidate-add-document"
                >
                  <Upload className="mr-2 h-4 w-4" /> Unggah Dokumen
                </Button>
              )}
            </div>
            <TableCard>
              <DataTable
                columns={documentColumns}
                rows={documents}
                loading={docsLoading}
                testId="candidate-documents-table"
                emptyProps={{
                  icon: FileText,
                  title: "Belum ada dokumen kandidat.",
                  description: "Unggah CV, KTP, ijazah, atau sertifikat agar verifikasi HR lengkap.",
                }}
              />
            </TableCard>
          </TabsContent>

          {/* ---------------- Riwayat ---------------- */}
          <TabsContent value="history" className="mt-4">
            <div className="rounded-lg border border-border bg-card">
              {data.history.length === 0 ? (
                <EmptyState icon={History} title="Belum ada riwayat." description="Riwayat terisi saat status kandidat berubah." />
              ) : (
                <ol className="divide-y divide-border" data-testid="candidate-history-list">
                  {data.history.map((h) => (
                    <li key={h.id} className="flex items-start gap-3 px-4 py-3" data-testid={`history-item-${h.id}`}>
                      <span className="mt-1 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary">
                        <History className="h-3.5 w-3.5" />
                      </span>
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <p className="text-[13px] font-medium">{HISTORY_ACTION_LABELS[h.action] || h.action}</p>
                          {h.from_label && <StageBadge stage={h.from_status} label={h.from_label} />}
                          {h.from_label && h.to_label && <span className="text-xs text-muted-foreground">→</span>}
                          {h.to_label && <StageBadge stage={h.to_status} label={h.to_label} />}
                        </div>
                        {h.notes && <p className="mt-0.5 text-[12px] text-muted-foreground">{h.notes}</p>}
                        <p className="mt-0.5 text-[11px] text-muted-foreground">
                          {h.changed_by_name || "Sistem"} · {formatDateTime(h.changed_at)}
                        </p>
                      </div>
                    </li>
                  ))}
                </ol>
              )}
            </div>
          </TabsContent>
        </Tabs>
      </PageBody>

      <CandidateFormDialog
        open={editOpen}
        onOpenChange={setEditOpen}
        mode="edit"
        catalog={catalog}
        values={values}
        errors={errors}
        onChange={(name, value) => setValues((p) => ({ ...p, [name]: value }))}
        onSubmit={submitEdit}
        submitting={submitting}
      />

      <ConvertEmployeeDialog
        open={convertOpen}
        onOpenChange={setConvertOpen}
        candidate={candidate}
        catalog={catalog}
        onConverted={() => reloadAll()}
      />

      <ScreeningDialog
        open={screeningOpen}
        onOpenChange={setScreeningOpen}
        candidate={candidate}
        catalog={catalog}
        onSaved={() => reloadAll()}
      />

      <Dialog open={uploadOpen} onOpenChange={setUploadOpen}>
        <DialogContent className="bg-card sm:max-w-lg" data-testid="candidate-upload-dialog">
          <DialogHeader>
            <DialogTitle className="text-base font-semibold">Unggah Dokumen Kandidat</DialogTitle>
            <DialogDescription className="leading-relaxed">
              Berkas tersimpan di penyimpanan dokumen perusahaan aktif dan terhubung ke kandidat ini.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="cand-doc-file">
                Berkas <span className="text-destructive">*</span>
              </Label>
              <Input
                id="cand-doc-file"
                ref={fileInput}
                type="file"
                onChange={(e) => {
                  const f = e.target.files?.[0] || null;
                  setUploadFile(f);
                  if (f && !uploadForm.name) setUploadForm((p) => ({ ...p, name: f.name.replace(/\.[^.]+$/, "") }));
                  setUploadError("");
                }}
                data-testid="candidate-upload-file"
              />
            </div>
            <div className="space-y-1.5">
              <Label>
                Tipe Dokumen <span className="text-destructive">*</span>
              </Label>
              <Select value={uploadForm.document_type_id} onValueChange={(v) => setUploadForm((p) => ({ ...p, document_type_id: v }))}>
                <SelectTrigger data-testid="candidate-upload-type">
                  <SelectValue placeholder="Pilih tipe dokumen" />
                </SelectTrigger>
                <SelectContent>
                  {docTypes.map((t) => (
                    <SelectItem key={t.id} value={t.id}>
                      {t.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="cand-doc-name">
                Nama Dokumen <span className="text-destructive">*</span>
              </Label>
              <Input
                id="cand-doc-name"
                value={uploadForm.name}
                onChange={(e) => setUploadForm((p) => ({ ...p, name: e.target.value }))}
                data-testid="candidate-upload-name"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="cand-doc-expiry">Berlaku Sampai</Label>
              <Input
                id="cand-doc-expiry"
                type="date"
                value={uploadForm.expiry_date}
                onChange={(e) => setUploadForm((p) => ({ ...p, expiry_date: e.target.value }))}
                data-testid="candidate-upload-expiry"
              />
            </div>
            {uploadError && (
              <div className="rounded-lg border border-danger-border bg-danger-soft px-3 py-2 text-sm text-destructive" data-testid="candidate-upload-error">
                {uploadError}
              </div>
            )}
          </div>
          <DialogFooter className="gap-2">
            <Button variant="outline" onClick={() => setUploadOpen(false)} disabled={uploading}>
              Batal
            </Button>
            <Button onClick={submitUpload} disabled={uploading} data-testid="candidate-upload-submit">
              {uploading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Unggah
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <DocumentPreviewDialog documentId={previewId} open={!!previewId} onOpenChange={(v) => !v && setPreviewId(null)} />

      <ConfirmDialog
        open={!!confirm}
        onOpenChange={(v) => !v && setConfirm(null)}
        title={
          confirm?.kind === "start"
            ? "Mulai screening kandidat ini?"
            : confirm?.kind === "delete"
            ? "Hapus kandidat ini?"
            : "Hapus dokumen ini?"
        }
        description={
          confirm?.kind === "start"
            ? `${candidate.full_name} akan berpindah dari Draft ke tahap Screening. Perubahan tercatat di riwayat dan Audit Log.`
            : confirm?.kind === "delete"
            ? "Kandidat dihapus dari daftar aktif. Riwayat dan Audit Log tetap tersimpan."
            : "Dokumen akan dihapus dari daftar aktif. Jejak perubahan tetap tersimpan di Audit Log."
        }
        destructive={confirm?.kind !== "start"}
        confirmLabel={confirm?.kind === "start" ? "Mulai Screening" : "Hapus"}
        loading={confirmLoading}
        onConfirm={runConfirm}
      />
    </>
  );
};

export default CandidateDetailPage;
