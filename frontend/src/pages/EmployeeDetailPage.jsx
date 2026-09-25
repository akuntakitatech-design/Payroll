import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  ArrowLeft,
  BadgeCheck,
  CalendarClock,
  CheckCircle2,
  Coins,
  Eye,
  FileSignature,
  FileText,
  Loader2,
  MoreHorizontal,
  Pencil,
  Plus,
  SlidersHorizontal,
  Trash2,
  Upload,
  UserCheck,
} from "lucide-react";
import { toast } from "sonner";
import { api, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { formatCurrency, formatDate, formatFileSize } from "@/lib/format";
import PageHeader, { PageBody } from "@/components/common/PageHeader";
import DataTable, { TableCard } from "@/components/common/DataTable";
import FormDialog from "@/components/common/FormDialog";
import ConfirmDialog from "@/components/common/ConfirmDialog";
import { ExpiryBadge } from "@/components/common/StatusBadge";
import { EmployeeStatusBadge } from "@/components/employees/EmployeeStatusBadge";
import ChangeStatusDialog from "@/components/employees/ChangeStatusDialog";
import {
  BankTaxTab,
  BpjsTab,
  EmploymentTab,
  FamilyTab,
  HistoryTab,
  PersonalTab,
  ProfileHeaderCard,
  SectionEditDialog,
  SummaryTab,
} from "@/components/employees/ProfileSections";
import { AssignmentTab } from "@/components/employees/AssignmentSection";
import DocumentPreviewDialog from "@/components/common/DocumentPreview";
import ContractRenewDialog from "@/components/payroll/ContractRenewDialog";
import { SalaryEditorDialog } from "@/pages/EmployeeSalariesPage";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
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
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

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

const LABELS = {
  gender: { male: "Laki-laki", female: "Perempuan" },
  marital_status: { single: "Belum menikah", married: "Menikah", divorced: "Duda / Janda" },
  education: { sd: "SD", smp: "SMP", sma: "SMA / SMK", d3: "Diploma (D3)", s1: "Sarjana (S1)", s2: "Magister (S2)", s3: "Doktor (S3)" },
};

const EmployeeDetailPage = () => {
  const { employeeId } = useParams();
  const navigate = useNavigate();
  const { can, hasModule, company } = useAuth();
  // Upgrade 01C - edit per bagian profil
  const [editSection, setEditSection] = useState(null);
  // tab aktif dikontrol agar tetap di tab yang sama setelah data dimuat ulang (mis. setelah aksi Penempatan)
  const [tab, setTab] = useState("summary");
  useEffect(() => setTab("summary"), [employeeId]);

  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [catalog, setCatalog] = useState(null);

  const [contractDialog, setContractDialog] = useState(null);
  const [certDialog, setCertDialog] = useState(null);
  const [values, setValues] = useState({});
  const [errors, setErrors] = useState({});
  const [submitting, setSubmitting] = useState(false);
  const [confirm, setConfirm] = useState(null);
  const [confirmLoading, setConfirmLoading] = useState(false);
  const [previewId, setPreviewId] = useState(null);
  const [renewContractId, setRenewContractId] = useState(null);
  const [salaryDialogOpen, setSalaryDialogOpen] = useState(false);
  const [salaryInfo, setSalaryInfo] = useState(null);
  const [salaryLoading, setSalaryLoading] = useState(false);

  const [uploadOpen, setUploadOpen] = useState(false);
  const [uploadForm, setUploadForm] = useState({ document_type_id: "", name: "", expiry_date: "" });
  const [uploadFile, setUploadFile] = useState(null);
  const [uploadError, setUploadError] = useState("");
  const [uploading, setUploading] = useState(false);
  // Upgrade 01B - Ubah Status + Riwayat Status
  const [changeOpen, setChangeOpen] = useState(false);
  const [historyKey, setHistoryKey] = useState(0);
  const fileInput = useRef(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.get(`/employees/${employeeId}`);
      setData(res.data);
      document.title = `${res.data.employee.full_name} · Data Karyawan`;
    } catch (err) {
      toast.error(errorMessage(err, "Data karyawan tidak dapat dimuat."));
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [employeeId]);

  const loadCatalog = useCallback(async () => {
    try {
      const res = await api.get("/employees/catalog");
      setCatalog(res.data);
    } catch {
      /* pelengkap */
    }
  }, []);

  useEffect(() => {
    load();
    loadCatalog();
  }, [load, loadCatalog]);

  const payrollVisible = hasModule("payroll") && can("employee_salary", "view");

  const loadSalary = useCallback(async () => {
    setSalaryLoading(true);
    try {
      const res = await api.get(`/payroll/salaries/${employeeId}`);
      setSalaryInfo(res.data);
    } catch {
      setSalaryInfo(null);
    } finally {
      setSalaryLoading(false);
    }
  }, [employeeId]);

  useEffect(() => {
    if (payrollVisible) loadSalary();
  }, [payrollVisible, loadSalary]);

  const employee = data?.employee;

  const contractFields = useMemo(
    () => [
      {
        name: "contract_type_id",
        label: "Tipe Kontrak",
        type: "select",
        required: true,
        options: (catalog?.contract_types || []).map((t) => ({ value: t.id, label: t.name })),
      },
      { name: "contract_number", label: "Nomor Kontrak", placeholder: "PKWT/2026/001" },
      { name: "start_date", label: "Tanggal Mulai", type: "date", required: true },
      {
        name: "end_date",
        label: "Tanggal Berakhir",
        type: "date",
        hint: "Kosongkan untuk karyawan tetap tanpa batas waktu.",
      },
      { name: "basic_salary", label: "Gaji Pokok", type: "number" },
      { name: "allowance", label: "Tunjangan", type: "number" },
      { name: "notes", label: "Catatan", type: "textarea", colSpan: 2 },
    ],
    [catalog]
  );

  const certFields = useMemo(
    () => [
      {
        name: "certification_type_id",
        label: "Tipe Sertifikasi",
        type: "select",
        required: true,
        options: (catalog?.certification_types || []).map((t) => ({ value: t.id, label: t.name })),
      },
      { name: "name", label: "Nama Sertifikat", required: true, placeholder: "Ahli K3 Umum" },
      { name: "certificate_number", label: "Nomor Sertifikat" },
      { name: "issuer", label: "Lembaga Penerbit" },
      { name: "issued_date", label: "Tanggal Terbit", type: "date" },
      { name: "expiry_date", label: "Berlaku Sampai", type: "date" },
      { name: "notes", label: "Catatan", type: "textarea", colSpan: 2 },
    ],
    [catalog]
  );

  const onChange = (name, value) => {
    setValues((prev) => ({ ...prev, [name]: value }));
    setErrors((prev) => ({ ...prev, [name]: undefined, __form__: undefined }));
  };

  const openContract = (row) => {
    const next = {};
    contractFields.forEach((f) => {
      next[f.name] = row?.[f.name] ?? "";
    });
    setValues(next);
    setErrors({});
    setContractDialog({ mode: row ? "edit" : "create", row });
  };

  const openCert = (row) => {
    const next = {};
    certFields.forEach((f) => {
      next[f.name] = row?.[f.name] ?? "";
    });
    setValues(next);
    setErrors({});
    setCertDialog({ mode: row ? "edit" : "create", row });
  };

  const submitContract = async () => {
    if (!values.contract_type_id) {
      setErrors({ contract_type_id: "Tipe kontrak wajib dipilih." });
      return;
    }
    if (!values.start_date) {
      setErrors({ start_date: "Tanggal mulai kontrak wajib diisi." });
      return;
    }
    setSubmitting(true);
    try {
      const payload = { employee_id: employeeId };
      Object.entries(values).forEach(([k, v]) => {
        if (v !== "" && v !== null && v !== undefined) {
          payload[k] = ["basic_salary", "allowance"].includes(k) ? Number(v) : v;
        }
      });
      if (contractDialog.mode === "edit") {
        delete payload.employee_id;
        await api.put(`/contracts/${contractDialog.row.id}`, payload);
        toast.success("Kontrak kerja berhasil diperbarui.");
      } else {
        await api.post("/contracts", payload);
        toast.success("Kontrak kerja berhasil ditambahkan.");
      }
      setContractDialog(null);
      load();
    } catch (err) {
      setErrors({ __form__: errorMessage(err, "Kontrak kerja tidak dapat disimpan.") });
    } finally {
      setSubmitting(false);
    }
  };

  const submitCert = async () => {
    if (!values.certification_type_id) {
      setErrors({ certification_type_id: "Tipe sertifikasi wajib dipilih." });
      return;
    }
    if (!values.name?.trim()) {
      setErrors({ name: "Nama sertifikat wajib diisi." });
      return;
    }
    setSubmitting(true);
    try {
      const payload = { employee_id: employeeId };
      Object.entries(values).forEach(([k, v]) => {
        if (v !== "" && v !== null && v !== undefined) payload[k] = v;
      });
      if (certDialog.mode === "edit") {
        delete payload.employee_id;
        await api.put(`/certifications/${certDialog.row.id}`, payload);
        toast.success("Sertifikasi berhasil diperbarui.");
      } else {
        await api.post("/certifications", payload);
        toast.success("Sertifikasi berhasil ditambahkan.");
      }
      setCertDialog(null);
      load();
    } catch (err) {
      setErrors({ __form__: errorMessage(err, "Sertifikasi tidak dapat disimpan.") });
    } finally {
      setSubmitting(false);
    }
  };

  const approveContract = async (row) => {
    try {
      await api.post(`/contracts/${row.id}/approve`);
      toast.success(`Kontrak ${row.contract_number || ""} disetujui.`);
      load();
    } catch (err) {
      toast.error(errorMessage(err, "Kontrak tidak dapat disetujui."));
    }
  };

  const runConfirm = async () => {
    setConfirmLoading(true);
    try {
      if (confirm.kind === "contract") {
        await api.delete(`/contracts/${confirm.row.id}`);
        toast.success("Kontrak kerja dihapus dari daftar aktif.");
      } else if (confirm.kind === "certification") {
        await api.delete(`/certifications/${confirm.row.id}`);
        toast.success("Sertifikasi dihapus.");
      } else {
        const res = await api.delete(`/documents/${confirm.row.id}`);
        toast.success(res.data.message);
      }
      setConfirm(null);
      load();
    } catch (err) {
      toast.error(errorMessage(err, "Tindakan tidak dapat diselesaikan."));
      setConfirm(null);
    } finally {
      setConfirmLoading(false);
    }
  };

  const submitUpload = async () => {
    setUploadError("");
    if (!uploadFile) {
      setUploadError("Pilih berkas yang ingin diunggah terlebih dahulu.");
      return;
    }
    if (!uploadForm.document_type_id) {
      setUploadError("Tipe dokumen wajib dipilih.");
      return;
    }
    if (!uploadForm.name?.trim()) {
      setUploadError("Nama dokumen wajib diisi.");
      return;
    }
    setUploading(true);
    try {
      const fd = new FormData();
      fd.append("file", uploadFile);
      fd.append("document_type_id", uploadForm.document_type_id);
      fd.append("name", uploadForm.name);
      fd.append("owner_type", "employee");
      fd.append("owner_id", employeeId);
      fd.append("owner_label", employee?.full_name || "");
      if (uploadForm.expiry_date) fd.append("expiry_date", uploadForm.expiry_date);
      await api.post("/documents", fd, { headers: { "Content-Type": "multipart/form-data" } });
      toast.success(`Dokumen "${uploadForm.name}" berhasil diunggah.`);
      setUploadOpen(false);
      setUploadFile(null);
      load();
    } catch (err) {
      setUploadError(errorMessage(err, "Dokumen tidak dapat diunggah."));
    } finally {
      setUploading(false);
    }
  };

  if (loading && (!data || data.employee?.id !== employeeId)) {
    return (
      <PageBody>
        <Skeleton className="h-24 w-full" />
        <Skeleton className="h-64 w-full" />
      </PageBody>
    );
  }

  if (!employee) {
    return (
      <PageBody>
        <div className="rounded-lg border border-border bg-card px-6 py-12 text-center">
          <p className="text-section-title">Data karyawan tidak ditemukan</p>
          <p className="mt-1 text-sm text-muted-foreground">
            Data mungkin sudah dihapus atau berada di perusahaan lain.
          </p>
          <Button className="mt-4" onClick={() => navigate("/employees")} data-testid="back-to-employees">
            Kembali ke Data Karyawan
          </Button>
        </div>
      </PageBody>
    );
  }

  const contractColumns = [
    {
      key: "contract_number",
      header: "Kontrak",
      render: (row) => (
        <div>
          <p className="font-medium">{row.contract_number || "Tanpa nomor"}</p>
          <p className="text-xs text-muted-foreground">{row.contract_type_name || "-"}</p>
        </div>
      ),
    },
    {
      key: "period",
      header: "Periode",
      render: (row) => (
        <div className="space-y-1">
          <p className="text-sm">
            {formatDate(row.start_date)} → {row.end_date ? formatDate(row.end_date) : "Tanpa batas"}
          </p>
          <ExpiryBadge state={row.state} daysLeft={row.days_left} testId={`contract-badge-${row.id}`} />
        </div>
      ),
    },
    {
      key: "basic_salary",
      header: "Gaji Pokok",
      hideOnMobile: true,
      render: (row) => (
        <div>
          <p className="text-sm">{formatCurrency(row.basic_salary)}</p>
          {row.allowance ? (
            <p className="text-xs text-muted-foreground">Tunjangan {formatCurrency(row.allowance)}</p>
          ) : null}
        </div>
      ),
    },
    {
      key: "approval_state",
      header: "Persetujuan",
      render: (row) =>
        row.approval_state === "approved" ? (
          <Badge variant="secondary" className="gap-1" data-testid={`contract-approved-${row.id}`}>
            <CheckCircle2 className="h-3 w-3" /> Disetujui
          </Badge>
        ) : (
          <Badge variant="outline" data-testid={`contract-draft-${row.id}`}>
            Draft
          </Badge>
        ),
    },
    {
      key: "actions",
      header: "",
      className: "w-12 text-right",
      render: (row) => (
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="icon" className="h-8 w-8" data-testid={`contract-actions-${row.id}`}>
              <MoreHorizontal className="h-4 w-4" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-52">
            {can("contract", "edit") && (
              <DropdownMenuItem onClick={() => openContract(row)} data-testid={`contract-edit-${row.id}`}>
                <Pencil className="mr-2 h-4 w-4" /> Ubah kontrak
              </DropdownMenuItem>
            )}
            {can("contract", "create") && !row.renewed_by_contract_id && (
              <DropdownMenuItem
                onClick={() => setRenewContractId(row.id)}
                data-testid={`contract-renew-${row.id}`}
              >
                <CalendarClock className="mr-2 h-4 w-4" /> Perpanjang kontrak
              </DropdownMenuItem>
            )}
            {can("contract", "approve") && row.approval_state !== "approved" && (
              <DropdownMenuItem onClick={() => approveContract(row)} data-testid={`contract-approve-${row.id}`}>
                <CheckCircle2 className="mr-2 h-4 w-4" /> Setujui kontrak
              </DropdownMenuItem>
            )}
            {can("contract", "delete") && (
              <>
                <DropdownMenuSeparator />
                <DropdownMenuItem
                  className="text-destructive focus:text-destructive"
                  onClick={() => setConfirm({ kind: "contract", row })}
                  data-testid={`contract-delete-${row.id}`}
                >
                  <Trash2 className="mr-2 h-4 w-4" /> Hapus kontrak
                </DropdownMenuItem>
              </>
            )}
          </DropdownMenuContent>
        </DropdownMenu>
      ),
    },
  ];

  const certColumns = [
    {
      key: "name",
      header: "Sertifikat",
      render: (row) => (
        <div>
          <p className="font-medium">{row.name}</p>
          <p className="text-xs text-muted-foreground">
            {row.certification_type_name || "-"}
            {row.certificate_number ? ` · ${row.certificate_number}` : ""}
          </p>
        </div>
      ),
    },
    { key: "issuer", header: "Penerbit", hideOnMobile: true, render: (row) => row.issuer || "-" },
    {
      key: "expiry_date",
      header: "Masa Berlaku",
      render: (row) => (
        <div className="space-y-1">
          <p className="text-sm">{row.expiry_date ? formatDate(row.expiry_date) : "Tanpa masa berlaku"}</p>
          <ExpiryBadge state={row.state} daysLeft={row.days_left} testId={`cert-badge-${row.id}`} />
        </div>
      ),
    },
    {
      key: "actions",
      header: "",
      className: "w-12 text-right",
      render: (row) => (
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="icon" className="h-8 w-8" data-testid={`cert-actions-${row.id}`}>
              <MoreHorizontal className="h-4 w-4" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-52">
            {can("certification", "edit") && (
              <DropdownMenuItem onClick={() => openCert(row)} data-testid={`cert-edit-${row.id}`}>
                <Pencil className="mr-2 h-4 w-4" /> Ubah sertifikasi
              </DropdownMenuItem>
            )}
            {can("certification", "delete") && (
              <>
                <DropdownMenuSeparator />
                <DropdownMenuItem
                  className="text-destructive focus:text-destructive"
                  onClick={() => setConfirm({ kind: "certification", row })}
                  data-testid={`cert-delete-${row.id}`}
                >
                  <Trash2 className="mr-2 h-4 w-4" /> Hapus sertifikasi
                </DropdownMenuItem>
              </>
            )}
          </DropdownMenuContent>
        </DropdownMenu>
      ),
    },
  ];

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
      key: "expiry_date",
      header: "Masa Berlaku",
      hideOnMobile: true,
      render: (row) => (
        <div className="space-y-1">
          <p className="text-sm">{row.expiry_date ? formatDate(row.expiry_date) : "Tidak ada"}</p>
          <ExpiryBadge state={row.state} daysLeft={row.days_left} testId={`doc-badge-${row.id}`} />
        </div>
      ),
    },
    {
      key: "actions",
      header: "",
      className: "w-40 text-right",
      render: (row) => (
        <div className="flex items-center justify-end gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => setPreviewId(row.id)}
            data-testid={`doc-preview-${row.id}`}
          >
            <Eye className="mr-1.5 h-3.5 w-3.5" /> Pratinjau
          </Button>
          {can("document", "delete") && (
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8 text-destructive"
              onClick={() => setConfirm({ kind: "document", row })}
              data-testid={`doc-delete-${row.id}`}
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
        title={employee.full_name}
        subtitle={`${employee.employee_number}${employee.job_title ? ` · ${employee.job_title}` : ""}${
          employee.department_name ? ` · ${employee.department_name}` : ""
        }`}
        actions={
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" onClick={() => navigate("/employees")} data-testid="employee-back-button">
              <ArrowLeft className="mr-2 h-4 w-4" /> Kembali
            </Button>
            <EmployeeStatusBadge
              name={employee.current_employee_status_name}
              category={employee.current_employee_status_category}
              archived={employee.status === "archived"}
              className="self-center"
              testId="employee-detail-status-badge"
            />
            {can("employee_status", "change") && employee.status !== "archived" && (
              <Button variant="outline" onClick={() => setChangeOpen(true)} data-testid="employee-detail-change-status-button">
                <UserCheck className="mr-2 h-4 w-4" /> Ubah Status
              </Button>
            )}
          </div>
        }
      />
      <ChangeStatusDialog
        open={changeOpen}
        onOpenChange={setChangeOpen}
        employee={employee}
        onChanged={() => {
          setHistoryKey((k) => k + 1);
          load();
        }}
      />
      <PageBody>
        <ProfileHeaderCard employee={employee} canEdit={can("employee", "edit")} onChanged={load} />
        <SectionEditDialog
          section={editSection}
          employee={employee}
          catalog={catalog}
          onOpenChange={(v) => !v && setEditSection(null)}
          onSaved={() => {
            setHistoryKey((k) => k + 1);
            load();
          }}
        />
        <Tabs value={tab} onValueChange={setTab} className="mt-4">
          <div className="-mx-1 overflow-x-auto px-1 pb-1">
            <TabsList className="inline-flex h-auto w-max flex-nowrap justify-start" data-testid="employee-tabs">
              <TabsTrigger value="summary" data-testid="tab-summary">Ringkasan</TabsTrigger>
              <TabsTrigger value="personal" data-testid="tab-personal">Data Pribadi</TabsTrigger>
              <TabsTrigger value="family" data-testid="tab-family">Keluarga</TabsTrigger>
              <TabsTrigger value="employment" data-testid="tab-employment">Kepegawaian</TabsTrigger>
              <TabsTrigger value="placement" data-testid="tab-placement">Penempatan Saat Ini</TabsTrigger>
              <TabsTrigger value="bank" data-testid="tab-bank">Bank &amp; Pajak</TabsTrigger>
              <TabsTrigger value="bpjs" data-testid="tab-bpjs">BPJS</TabsTrigger>
              <TabsTrigger value="documents" data-testid="tab-documents">Dokumen ({data.documents.length})</TabsTrigger>
              <TabsTrigger value="contracts" data-testid="tab-contracts">Kontrak ({data.contracts.length})</TabsTrigger>
              <TabsTrigger value="certifications" data-testid="tab-certifications">Sertifikasi ({data.certifications.length})</TabsTrigger>
              <TabsTrigger value="history" data-testid="tab-history">Riwayat</TabsTrigger>
              {payrollVisible && (
                <TabsTrigger value="payroll" data-testid="tab-payroll">Gaji &amp; Payroll</TabsTrigger>
              )}
            </TabsList>
          </div>

          <TabsContent value="summary" className="mt-4">
            <SummaryTab employee={employee} documents={data.documents} contracts={data.contracts} />
          </TabsContent>
          <TabsContent value="personal" className="mt-4">
            <PersonalTab employee={employee} catalog={catalog} onEdit={can("employee", "edit") ? () => setEditSection("personal") : undefined} />
          </TabsContent>
          <TabsContent value="family" className="mt-4">
            <FamilyTab employeeId={employee.id} canEdit={can("employee", "edit")} catalog={catalog} />
          </TabsContent>
          <TabsContent value="employment" className="mt-4">
            <EmploymentTab employee={employee} company={company} onEdit={can("employee", "edit") ? () => setEditSection("employment") : undefined} />
          </TabsContent>
          <TabsContent value="placement" className="mt-4">
            <AssignmentTab
              employee={employee}
              company={company}
              catalog={catalog}
              canEdit={can("employee", "edit")}
              canChangeStatus={can("employee_status", "change")}
              onChanged={load}
            />
          </TabsContent>
          <TabsContent value="bank" className="mt-4">
            <BankTaxTab employee={employee} salaryInfo={salaryInfo} payrollVisible={payrollVisible}
              onEdit={can("employee", "edit") ? () => setEditSection("bank_tax") : undefined} />
          </TabsContent>
          <TabsContent value="bpjs" className="mt-4">
            <BpjsTab employee={employee} onEdit={can("employee", "edit") ? () => setEditSection("bpjs") : undefined} />
          </TabsContent>
          <TabsContent value="history" className="mt-4">
            <HistoryTab employeeId={employee.id} refreshKey={historyKey} />
          </TabsContent>

          <TabsContent value="contracts" className="mt-4 space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="text-sm text-muted-foreground">
                Riwayat kontrak kerja. Pengingat otomatis aktif {data.horizon_days} hari sebelum kontrak
                berakhir, sesuai Kebijakan Perusahaan.
              </p>
              {can("contract", "create") && (
                <Button onClick={() => openContract(null)} data-testid="add-contract-button">
                  <Plus className="mr-2 h-4 w-4" /> Tambah Kontrak
                </Button>
              )}
            </div>
            <TableCard>
              <DataTable
                columns={contractColumns}
                rows={data.contracts}
                testId="contracts-table"
                emptyProps={{
                  icon: FileSignature,
                  title: "Belum ada kontrak kerja.",
                  description:
                    "Tambahkan kontrak agar masa berlaku terpantau dan muncul di Kalender Masa Berlaku.",
                  actionLabel: can("contract", "create") ? "Tambah Kontrak" : undefined,
                  onAction: () => openContract(null),
                }}
              />
            </TableCard>
          </TabsContent>

          <TabsContent value="certifications" className="mt-4 space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="text-sm text-muted-foreground">
                Sertifikasi wajib dan kompetensi karyawan beserta masa berlakunya.
              </p>
              {can("certification", "create") && (
                <Button onClick={() => openCert(null)} data-testid="add-certification-button">
                  <Plus className="mr-2 h-4 w-4" /> Tambah Sertifikasi
                </Button>
              )}
            </div>
            <TableCard>
              <DataTable
                columns={certColumns}
                rows={data.certifications}
                testId="certifications-table"
                emptyProps={{
                  icon: BadgeCheck,
                  title: "Belum ada sertifikasi.",
                  description: "Catat sertifikat wajib agar tidak terlewat saat penempatan proyek.",
                  actionLabel: can("certification", "create") ? "Tambah Sertifikasi" : undefined,
                  onAction: () => openCert(null),
                }}
              />
            </TableCard>
          </TabsContent>

          <TabsContent value="documents" className="mt-4 space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="text-sm text-muted-foreground">
                Dokumen milik karyawan ini. Klik Pratinjau untuk melihat berkas langsung di layar.
              </p>
              {can("document", "create") && (
                <Button
                  onClick={() => {
                    setUploadForm({
                      document_type_id: catalog?.document_types?.[0]?.id || "",
                      name: "",
                      expiry_date: "",
                    });
                    setUploadFile(null);
                    setUploadError("");
                    setUploadOpen(true);
                  }}
                  data-testid="add-document-button"
                >
                  <Upload className="mr-2 h-4 w-4" /> Unggah Dokumen
                </Button>
              )}
            </div>
            <TableCard>
              <DataTable
                columns={documentColumns}
                rows={data.documents}
                testId="employee-documents-table"
                emptyProps={{
                  icon: FileText,
                  title: "Belum ada dokumen karyawan.",
                  description: "Unggah KTP, ijazah, sertifikat, atau hasil MCU agar arsip lengkap.",
                }}
              />
            </TableCard>
          </TabsContent>

          {payrollVisible && (
            <TabsContent value="payroll" className="mt-4 space-y-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="text-sm text-muted-foreground">
                  Struktur gaji dan data pajak yang dipakai setiap kali payroll dihitung.
                </p>
                <div className="flex flex-wrap items-center gap-2">
                  {can("payroll", "view") && (
                    <Button
                      variant="outline"
                      onClick={() => navigate("/payroll/runs")}
                      data-testid="payroll-open-runs"
                    >
                      <Coins className="mr-2 h-4 w-4" /> Payroll bulanan
                    </Button>
                  )}
                  {can("employee_salary", "edit") && (
                    <Button
                      onClick={() => setSalaryDialogOpen(true)}
                      data-testid="employee-salary-edit"
                    >
                      <SlidersHorizontal className="mr-2 h-4 w-4" /> Atur struktur gaji
                    </Button>
                  )}
                </div>
              </div>

              {salaryLoading ? (
                <Skeleton className="h-40 w-full" />
              ) : !salaryInfo?.salary ? (
                <div
                  className="rounded-lg border border-dashed border-border bg-card p-6 text-center"
                  data-testid="employee-salary-empty"
                >
                  <p className="text-sm font-medium">Struktur gaji belum diatur</p>
                  <p className="mt-1 text-sm text-muted-foreground">
                    Karyawan tanpa gaji pokok akan dilewati saat payroll dihitung.
                  </p>
                </div>
              ) : (
                <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
                  <InfoCard title="Gaji & Tunjangan">
                    <InfoRow
                      label="Gaji Pokok"
                      value={formatCurrency(salaryInfo.salary.basic_salary)}
                      testId="salary-basic"
                    />
                    {(salaryInfo.salary.components || []).map((comp) => (
                      <InfoRow
                        key={comp.component_id}
                        label={`${comp.name || comp.component_id}${
                          comp.calc === "percent_of_basic" ? ` (${comp.percent || 0}% gaji pokok)` : ""
                        }`}
                        value={`${formatCurrency(comp.effective_amount ?? comp.amount)}${
                          comp.uses_default ? " · nilai default" : ""
                        }`}
                      />
                    ))}
                    <InfoRow
                      label="Terakhir diubah"
                      value={formatDate(salaryInfo.salary.updated_at)}
                    />
                  </InfoCard>
                  <InfoCard title="Pajak & BPJS">
                    <InfoRow
                      label="Status PTKP"
                      value={`${salaryInfo.salary.ptkp_status || "-"}${
                        salaryInfo.salary.ter_category
                          ? ` (TER ${salaryInfo.salary.ter_category})`
                          : ""
                      }`}
                      testId="salary-ptkp"
                    />
                    {/* Upgrade 01C: nilai sensitif memakai data profil (sudah dimasking server-side sesuai hak employee:edit) */}
                    <InfoRow label="NPWP" value={employee.npwp || "Belum ada"} />
                    <InfoRow
                      label="BPJS Kesehatan"
                      value={salaryInfo.salary.bpjs_kesehatan_enrolled ? "Terdaftar" : "Tidak"}
                    />
                    <InfoRow
                      label="BPJS JHT"
                      value={salaryInfo.salary.bpjs_jht_enrolled ? "Terdaftar" : "Tidak"}
                    />
                    <InfoRow
                      label="BPJS Jaminan Pensiun"
                      value={salaryInfo.salary.bpjs_jp_enrolled ? "Terdaftar" : "Tidak"}
                    />
                    <InfoRow
                      label="Rekening"
                      value={
                        employee.bank_account_number
                          ? `${employee.bank_name || ""} ${employee.bank_account_number}`.trim()
                          : "-"
                      }
                    />
                  </InfoCard>
                </div>
              )}

              {salaryInfo?.history?.length > 0 && (
                <InfoCard title="Riwayat Perubahan Gaji">
                  {salaryInfo.history.map((row, index) => (
                    <InfoRow
                      key={row.id || index}
                      label={formatDate(row.effective_date || row.created_at)}
                      value={`${formatCurrency(row.previous_basic_salary)} → ${formatCurrency(
                        row.basic_salary
                      )}${row.notes ? ` · ${row.notes}` : ""}`}
                    />
                  ))}
                </InfoCard>
              )}
            </TabsContent>
          )}
        </Tabs>
      </PageBody>

      <FormDialog
        open={!!contractDialog}
        onOpenChange={(v) => !v && setContractDialog(null)}
        title={contractDialog?.mode === "edit" ? "Ubah Kontrak Kerja" : "Tambah Kontrak Kerja"}
        description={`Kontrak untuk ${employee.full_name}. Kosongkan tanggal berakhir untuk karyawan tetap.`}
        fields={contractFields}
        values={values}
        errors={errors}
        onChange={onChange}
        onSubmit={submitContract}
        submitting={submitting}
        submitLabel="Simpan Kontrak"
      />

      <FormDialog
        open={!!certDialog}
        onOpenChange={(v) => !v && setCertDialog(null)}
        title={certDialog?.mode === "edit" ? "Ubah Sertifikasi" : "Tambah Sertifikasi"}
        description={`Sertifikasi untuk ${employee.full_name}. Masa berlaku akan dipantau otomatis.`}
        fields={certFields}
        values={values}
        errors={errors}
        onChange={onChange}
        onSubmit={submitCert}
        submitting={submitting}
        submitLabel="Simpan Sertifikasi"
      />

      <Dialog open={uploadOpen} onOpenChange={setUploadOpen}>
        <DialogContent className="bg-card sm:max-w-lg" data-testid="employee-upload-dialog">
          <DialogHeader>
            <DialogTitle className="font-semibold">Unggah Dokumen Karyawan</DialogTitle>
            <DialogDescription>
              Dokumen otomatis terhubung ke {employee.full_name} dan hanya dapat dilihat dalam
              perusahaan ini.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="emp-doc-file">
                Berkas <span className="text-destructive">*</span>
              </Label>
              <Input
                id="emp-doc-file"
                ref={fileInput}
                type="file"
                onChange={(e) => {
                  const f = e.target.files?.[0] || null;
                  setUploadFile(f);
                  if (f && !uploadForm.name) {
                    setUploadForm((p) => ({ ...p, name: f.name.replace(/\.[^.]+$/, "") }));
                  }
                  setUploadError("");
                }}
                data-testid="employee-upload-file"
              />
            </div>
            <div className="space-y-1.5">
              <Label>
                Tipe Dokumen <span className="text-destructive">*</span>
              </Label>
              <Select
                value={uploadForm.document_type_id}
                onValueChange={(v) => setUploadForm((p) => ({ ...p, document_type_id: v }))}
              >
                <SelectTrigger data-testid="employee-upload-type">
                  <SelectValue placeholder="Pilih tipe dokumen" />
                </SelectTrigger>
                <SelectContent>
                  {(catalog?.document_types || []).map((t) => (
                    <SelectItem key={t.id} value={t.id}>
                      {t.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="emp-doc-name">
                Nama Dokumen <span className="text-destructive">*</span>
              </Label>
              <Input
                id="emp-doc-name"
                value={uploadForm.name}
                onChange={(e) => setUploadForm((p) => ({ ...p, name: e.target.value }))}
                data-testid="employee-upload-name"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="emp-doc-expiry">Berlaku Sampai</Label>
              <Input
                id="emp-doc-expiry"
                type="date"
                value={uploadForm.expiry_date}
                onChange={(e) => setUploadForm((p) => ({ ...p, expiry_date: e.target.value }))}
                data-testid="employee-upload-expiry"
              />
            </div>
            {uploadError && (
              <div
                className="rounded-lg border border-danger-border bg-danger-soft px-3 py-2 text-sm text-destructive"
                data-testid="employee-upload-error"
              >
                {uploadError}
              </div>
            )}
          </div>
          <DialogFooter className="gap-2">
            <Button variant="outline" onClick={() => setUploadOpen(false)} disabled={uploading}>
              Batal
            </Button>
            <Button onClick={submitUpload} disabled={uploading} data-testid="employee-upload-submit">
              {uploading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Unggah
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <DocumentPreviewDialog
        documentId={previewId}
        open={!!previewId}
        onOpenChange={(v) => !v && setPreviewId(null)}
      />

      <ContractRenewDialog
        contractId={renewContractId}
        open={!!renewContractId}
        onClose={() => setRenewContractId(null)}
        onRenewed={() => load()}
      />

      {payrollVisible && (
        <SalaryEditorDialog
          employeeId={employeeId}
          employeeName={employee.full_name}
          open={salaryDialogOpen}
          onClose={() => setSalaryDialogOpen(false)}
          onSaved={() => loadSalary()}
        />
      )}

      <ConfirmDialog
        open={!!confirm}
        onOpenChange={(v) => !v && setConfirm(null)}
        title="Hapus data ini?"
        description="Data akan dihapus dari daftar aktif. Jejak perubahan tetap tersimpan di Audit Log."
        destructive
        confirmLabel="Hapus"
        loading={confirmLoading}
        onConfirm={runConfirm}
      />
    </>
  );
};

export default EmployeeDetailPage;
