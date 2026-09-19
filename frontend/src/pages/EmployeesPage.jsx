import React, { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  AlertTriangle,
  BadgeCheck,
  CalendarClock,
  FileSpreadsheet,
  Pencil,
  Plus,
  Power,
  Trash2,
  UserRound,
  Users,
} from "lucide-react";
import { toast } from "sonner";
import { api, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { formatDate } from "@/lib/format";
import PageHeader, { PageBody } from "@/components/common/PageHeader";
import DataTable, {
  BulkActionBar,
  FilterBar,
  FilterSelect,
  Pagination,
  RowActions,
  TableCard,
} from "@/components/common/DataTable";
import FormDialog from "@/components/common/FormDialog";
import ConfirmDialog from "@/components/common/ConfirmDialog";
import StatusBadge, { ExpiryBadge } from "@/components/common/StatusBadge";
import { Button } from "@/components/ui/button";

const StatTile = ({ label, value, hint, icon: Icon, tone = "default", testId }) => {
  const tones = {
    default: "text-foreground",
    warning: "text-warning",
    critical: "text-danger",
  };
  return (
    <div className="rounded-lg border border-border bg-card px-4 py-3" data-testid={testId}>
      <div className="flex items-center justify-between gap-2">
        <p className="text-[12px] text-muted-foreground">{label}</p>
        {Icon && <Icon className="h-4 w-4 text-muted-foreground" strokeWidth={1.75} />}
      </div>
      <p className={`mt-0.5 text-xl font-semibold leading-tight ${tones[tone]}`} data-numeric="true">
        {value}
      </p>
      {hint && <p className="mt-0.5 text-[12px] text-muted-foreground">{hint}</p>}
    </div>
  );
};

const EmployeesPage = () => {
  const { can, company } = useAuth();
  const navigate = useNavigate();

  const [rows, setRows] = useState([]);
  const [meta, setMeta] = useState({ total: 0, page: 1, limit: 20, total_pages: 1 });
  const [loading, setLoading] = useState(true);
  const [stats, setStats] = useState(null);
  const [catalog, setCatalog] = useState(null);

  const [search, setSearch] = useState("");
  const [debounced, setDebounced] = useState("");
  const [filters, setFilters] = useState({ department_id: "", status: "", project_id: "" });
  const [page, setPage] = useState(1);
  const [limit, setLimit] = useState(20);

  const [dialog, setDialog] = useState(null); // {mode:'create'|'edit', row}
  const [values, setValues] = useState({});
  const [errors, setErrors] = useState({});
  const [submitting, setSubmitting] = useState(false);
  const [confirm, setConfirm] = useState(null);
  const [confirmLoading, setConfirmLoading] = useState(false);
  const [selected, setSelected] = useState([]);

  useEffect(() => {
    const t = setTimeout(() => setDebounced(search), 350);
    return () => clearTimeout(t);
  }, [search]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = { page, limit };
      if (debounced) params.q = debounced;
      Object.entries(filters).forEach(([k, v]) => {
        if (v) params[k] = v;
      });
      const res = await api.get("/employees", { params });
      setRows(res.data.items || []);
      setSelected([]);
      setMeta({
        total: res.data.total,
        page: res.data.page,
        limit: res.data.limit,
        total_pages: res.data.total_pages,
      });
    } catch (err) {
      toast.error(errorMessage(err, "Data karyawan belum dapat ditampilkan. Coba muat ulang halaman."));
      setRows([]);
    } finally {
      setLoading(false);
    }
  }, [page, limit, debounced, filters]);

  const loadSide = useCallback(async () => {
    try {
      const [statsRes, catalogRes] = await Promise.all([
        api.get("/employees/stats"),
        api.get("/employees/catalog"),
      ]);
      setStats(statsRes.data);
      setCatalog(catalogRes.data);
    } catch (err) {
      /* stats/catalog bersifat pelengkap, daftar utama tetap tampil */
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    loadSide();
    document.title = "Data Karyawan · HRIS Suite";
  }, [loadSide, company?.id]);

  const options = useCallback(
    (key) => (catalog?.[key] || []).map((o) => ({ value: o.id, label: o.name })),
    [catalog]
  );

  const fields = useMemo(
    () => [
      { name: "full_name", label: "Nama Lengkap", required: true, placeholder: "Nama sesuai KTP", colSpan: 2 },
      {
        name: "employee_number",
        label: "NIK Karyawan",
        hint: "Kosongkan agar sistem membuat nomor otomatis sesuai format perusahaan.",
      },
      { name: "nik", label: "Nomor KTP" },
      { name: "gender", label: "Jenis Kelamin", type: "select", options: (catalog?.genders || []).map((g) => ({ value: g.key, label: g.label })) },
      { name: "birth_date", label: "Tanggal Lahir", type: "date" },
      { name: "birth_place", label: "Tempat Lahir" },
      { name: "marital_status", label: "Status Pernikahan", type: "select", options: (catalog?.marital_statuses || []).map((g) => ({ value: g.key, label: g.label })) },
      { name: "religion", label: "Agama", type: "select", options: (catalog?.religions || []).map((g) => ({ value: g.key, label: g.label })) },
      { name: "education", label: "Pendidikan Terakhir", type: "select", options: (catalog?.educations || []).map((g) => ({ value: g.key, label: g.label })) },
      { name: "email", label: "Email", placeholder: "nama@perusahaan.co.id" },
      { name: "phone", label: "Nomor HP" },
      { name: "address", label: "Alamat", type: "textarea", colSpan: 2 },
      { name: "city", label: "Kota Domisili" },
      { name: "job_title", label: "Sebutan Jabatan" },
      { name: "join_date", label: "Tanggal Masuk", type: "date" },
      { name: "employment_status_id", label: "Status Kepegawaian", type: "select", options: options("employment_statuses") },
      { name: "branch_id", label: "Cabang", type: "select", options: options("branches") },
      { name: "work_location_id", label: "Lokasi Kerja", type: "select", options: options("work_locations") },
      { name: "department_id", label: "Departemen", type: "select", options: options("departments") },
      { name: "division_id", label: "Divisi", type: "select", options: options("divisions") },
      { name: "position_id", label: "Jabatan", type: "select", options: options("positions") },
      { name: "job_grade_id", label: "Grade / Level", type: "select", options: options("job_grades") },
      { name: "cost_center_id", label: "Cost Center", type: "select", options: options("cost_centers") },
      { name: "project_id", label: "Penempatan Proyek", type: "select", options: options("projects") },
      { name: "bank_name", label: "Nama Bank" },
      { name: "bank_account_number", label: "Nomor Rekening" },
      { name: "bank_account_name", label: "Nama Pemilik Rekening" },
      { name: "npwp", label: "NPWP" },
      { name: "bpjs_kesehatan_number", label: "BPJS Kesehatan" },
      { name: "bpjs_tk_number", label: "BPJS Ketenagakerjaan" },
      { name: "emergency_contact_name", label: "Kontak Darurat" },
      { name: "emergency_contact_phone", label: "Telepon Kontak Darurat" },
      { name: "notes", label: "Catatan", type: "textarea", colSpan: 2 },
    ],
    [catalog, options]
  );

  const openCreate = () => {
    setValues({});
    setErrors({});
    setDialog({ mode: "create" });
  };

  const openEdit = (row) => {
    const next = {};
    fields.forEach((f) => {
      next[f.name] = row[f.name] ?? "";
    });
    setValues(next);
    setErrors({});
    setDialog({ mode: "edit", row });
  };

  const onChange = (name, value) => {
    setValues((prev) => ({ ...prev, [name]: value }));
    setErrors((prev) => ({ ...prev, [name]: undefined, __form__: undefined }));
  };

  const submit = async () => {
    if (!values.full_name?.trim()) {
      setErrors({ full_name: "Nama lengkap wajib diisi." });
      return;
    }
    setSubmitting(true);
    try {
      const payload = {};
      Object.entries(values).forEach(([k, v]) => {
        if (v !== "" && v !== null && v !== undefined) payload[k] = v;
      });
      if (dialog.mode === "create") {
        const res = await api.post("/employees", payload);
        toast.success(`Karyawan "${res.data.full_name}" berhasil ditambahkan (${res.data.employee_number}).`);
      } else {
        await api.put(`/employees/${dialog.row.id}`, payload);
        toast.success("Data karyawan berhasil diperbarui.");
      }
      setDialog(null);
      load();
      loadSide();
    } catch (err) {
      setErrors({ __form__: errorMessage(err, "Data karyawan tidak dapat disimpan.") });
    } finally {
      setSubmitting(false);
    }
  };

  const runConfirm = async () => {
    setConfirmLoading(true);
    try {
      if (confirm.type === "delete") {
        const res = await api.delete(`/employees/${confirm.row.id}`);
        toast.success(res.data.message);
      } else {
        const nextStatus = confirm.row.status === "active" ? "inactive" : "active";
        await api.patch(`/employees/${confirm.row.id}/status`, { status: nextStatus });
        toast.success(
          nextStatus === "active"
            ? `${confirm.row.full_name} kembali diaktifkan.`
            : `${confirm.row.full_name} dinonaktifkan.`
        );
      }
      setConfirm(null);
      load();
      loadSide();
    } catch (err) {
      toast.error(errorMessage(err, "Tindakan tidak dapat diselesaikan."));
      setConfirm(null);
    } finally {
      setConfirmLoading(false);
    }
  };

  const columns = [
    {
      key: "full_name",
      header: "Karyawan",
      render: (row) => (
        <div className="flex min-w-0 items-start gap-2">
          <UserRound className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
          <div className="min-w-0">
            <p className="truncate text-[13px] font-medium" data-testid={`employee-name-${row.id}`}>
              {row.full_name}
            </p>
            <p className="truncate text-[12px] text-muted-foreground">
              {row.employee_number}
              {row.job_title ? ` · ${row.job_title}` : ""}
            </p>
          </div>
        </div>
      ),
    },
    {
      key: "department_name",
      header: "Unit Kerja",
      hideOnMobile: true,
      render: (row) => (
        <div>
          <p className="text-[13px]">{row.department_name || "-"}</p>
          <p className="text-[12px] text-muted-foreground">{row.position_name || row.division_name || "-"}</p>
        </div>
      ),
    },
    {
      key: "employment_status_name",
      header: "Status Kepegawaian",
      hideOnMobile: true,
      render: (row) => row.employment_status_name || "-",
    },
    {
      key: "contract",
      header: "Kontrak Aktif",
      render: (row) => {
        if (!row.active_contract) {
          return (
            <span className="inline-flex items-center gap-1 text-[12px] text-muted-foreground">
              <AlertTriangle className="h-3.5 w-3.5" /> Belum ada kontrak
            </span>
          );
        }
        const c = row.active_contract;
        return (
          <div className="space-y-1">
            <p className="text-[13px]">{c.contract_type_name || c.contract_number || "Kontrak"}</p>
            <div className="flex items-center gap-2">
              <span className="text-[12px] text-muted-foreground">
                {c.end_date ? `s.d. ${formatDate(c.end_date)}` : "Tanpa batas waktu"}
              </span>
              {c.state !== "none" && <ExpiryBadge state={c.state} daysLeft={c.days_left} testId={`contract-expiry-${row.id}`} />}
            </div>
          </div>
        );
      },
    },
    { key: "status", header: "Status", render: (row) => <StatusBadge status={row.status} /> },
    {
      key: "actions",
      header: "",
      align: "right",
      className: "w-12",
      render: (row) => (
        <RowActions
          testId={`employee-actions-${row.id}`}
          actions={[
            {
              key: "detail",
              label: "Lihat Detail",
              icon: UserRound,
              onSelect: () => navigate(`/employees/${row.id}`),
              testId: `employee-detail-${row.id}`,
            },
            can("employee", "edit") && {
              key: "edit",
              label: "Ubah Data",
              icon: Pencil,
              onSelect: () => openEdit(row),
              testId: `employee-edit-${row.id}`,
            },
            can("employee", "edit") && {
              key: "status",
              label: row.status === "active" ? "Nonaktifkan" : "Aktifkan",
              icon: Power,
              onSelect: () => setConfirm({ type: "status", row }),
              testId: `employee-status-${row.id}`,
            },
            can("employee", "delete") && {
              key: "delete",
              label: "Hapus Karyawan",
              icon: Trash2,
              destructive: true,
              separatorBefore: true,
              onSelect: () => setConfirm({ type: "delete", row }),
              testId: `employee-delete-${row.id}`,
            },
          ]}
        />
      ),
    },
  ];

  const hasFilters = !!debounced || Object.values(filters).some(Boolean);

  return (
    <>
      <PageHeader
        title="Data Karyawan"
        subtitle="Data induk karyawan, penempatan organisasi, kontrak kerja, dan sertifikasi."
        actions={
          can("employee", "create") && (
            <div className="flex flex-wrap items-center gap-2">
              <Button
                variant="outline"
                onClick={() => navigate("/employees/import")}
                data-testid="employees-import-excel"
              >
                <FileSpreadsheet className="mr-1.5 h-4 w-4" /> Impor Excel
              </Button>
              <Button onClick={openCreate} data-testid="page-header-primary-action">
                <Plus className="mr-1.5 h-4 w-4" /> Tambah Karyawan
              </Button>
            </div>
          )
        }
      />
      <PageBody>
        {stats && (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <StatTile
              label="Karyawan Aktif"
              value={stats.active}
              hint={`${stats.total} total data karyawan`}
              icon={Users}
              testId="stat-employees-active"
            />
            <StatTile
              label="Kontrak Segera Berakhir"
              value={stats.contracts_expiring}
              hint={`Dalam ${stats.horizon_days} hari ke depan`}
              icon={CalendarClock}
              tone={stats.contracts_expiring ? "warning" : "default"}
              testId="stat-contracts-expiring"
            />
            <StatTile
              label="Kontrak Kedaluwarsa"
              value={stats.contracts_expired}
              hint="Perlu diperbarui atau diarsipkan"
              icon={AlertTriangle}
              tone={stats.contracts_expired ? "critical" : "default"}
              testId="stat-contracts-expired"
            />
            <StatTile
              label="Sertifikasi Perlu Perhatian"
              value={stats.certifications_attention}
              hint={`${stats.certifications} sertifikasi tercatat`}
              icon={BadgeCheck}
              tone={stats.certifications_attention ? "warning" : "default"}
              testId="stat-certifications-attention"
            />
          </div>
        )}

        <FilterBar
          search={search}
          onSearchChange={(v) => {
            setSearch(v);
            setPage(1);
          }}
          searchPlaceholder="Cari nama, NIK karyawan, email, atau jabatan…"
          showReset={hasFilters}
          activeFilterCount={Object.values(filters).filter(Boolean).length + (debounced ? 1 : 0)}
          onReset={() => {
            setSearch("");
            setFilters({ department_id: "", status: "", project_id: "" });
            setPage(1);
          }}
        >
          <FilterSelect
            label="Departemen"
            value={filters.department_id}
            onChange={(v) => {
              setFilters((p) => ({ ...p, department_id: v }));
              setPage(1);
            }}
            options={options("departments")}
            allLabel="Semua departemen"
            testId="filter-department"
          />
          <FilterSelect
            label="Proyek"
            value={filters.project_id}
            onChange={(v) => {
              setFilters((p) => ({ ...p, project_id: v }));
              setPage(1);
            }}
            options={options("projects")}
            allLabel="Semua proyek"
            testId="filter-project"
          />
          <FilterSelect
            label="Status"
            value={filters.status}
            onChange={(v) => {
              setFilters((p) => ({ ...p, status: v }));
              setPage(1);
            }}
            options={[
              { value: "active", label: "Aktif" },
              { value: "inactive", label: "Nonaktif" },
              { value: "archived", label: "Diarsipkan" },
            ]}
            allLabel="Semua status"
            testId="filter-status"
          />
        </FilterBar>

        <TableCard>
          <BulkActionBar count={selected.length} onClear={() => setSelected([])}>
            <span className="text-[12px] text-muted-foreground">
              Aksi massal (penempatan proyek, perpanjangan kontrak) menyusul pada modul terkait.
            </span>
          </BulkActionBar>
          <DataTable
            columns={columns}
            rows={rows}
            loading={loading}
            testId="employees-table"
            selection={{ enabled: true, selected, onChange: setSelected }}
            onRowClick={(row) => navigate(`/employees/${row.id}`)}
            emptyProps={{
              icon: Users,
              title: hasFilters ? "Tidak ada karyawan yang cocok." : "Belum ada data karyawan.",
              description: hasFilters
                ? "Coba ubah kata kunci atau hapus filter yang aktif."
                : "Tambahkan karyawan pertama. Data ini akan dipakai untuk kontrak, sertifikasi, absensi dan payroll.",
              actionLabel: !hasFilters && can("employee", "create") ? "Tambah Karyawan" : undefined,
              onAction: openCreate,
            }}
          />
          {rows.length > 0 && (
            <Pagination
              page={meta.page}
              totalPages={meta.total_pages}
              total={meta.total}
              limit={meta.limit}
              onPageChange={setPage}
              onLimitChange={(v) => {
                setLimit(v);
                setPage(1);
              }}
            />
          )}
        </TableCard>
      </PageBody>

      <FormDialog
        open={!!dialog}
        onOpenChange={(v) => !v && setDialog(null)}
        title={dialog?.mode === "edit" ? "Ubah Data Karyawan" : "Tambah Karyawan"}
        description="Isi data pribadi dan penempatan organisasi. Nomor karyawan dibuat otomatis bila dibiarkan kosong."
        fields={fields}
        values={values}
        errors={errors}
        onChange={onChange}
        onSubmit={submit}
        submitting={submitting}
        submitLabel={dialog?.mode === "edit" ? "Simpan Perubahan" : "Simpan Karyawan"}
        wide
      />

      <ConfirmDialog
        open={!!confirm}
        onOpenChange={(v) => !v && setConfirm(null)}
        title={
          confirm?.type === "delete"
            ? "Hapus data karyawan?"
            : confirm?.row?.status === "active"
            ? "Nonaktifkan karyawan ini?"
            : "Aktifkan kembali karyawan ini?"
        }
        description={
          confirm?.type === "delete"
            ? `Data "${confirm?.row?.full_name}" akan dihapus dari daftar. Karyawan yang masih memiliki kontrak kerja tidak dapat dihapus.`
            : `Status karyawan "${confirm?.row?.full_name}" akan diubah. Riwayat kontrak dan dokumen tetap tersimpan.`
        }
        destructive={confirm?.type === "delete"}
        confirmLabel={confirm?.type === "delete" ? "Hapus karyawan" : "Ubah status"}
        loading={confirmLoading}
        onConfirm={runConfirm}
      />
    </>
  );
};

export default EmployeesPage;
