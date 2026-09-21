import React, { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { ArrowLeft, Eye, Pencil, Plus, Trash2, UserPlus, Users } from "lucide-react";
import { toast } from "sonner";
import { api, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { formatDate } from "@/lib/format";
import { RECRUITMENT_ROUTES, toCandidatePayload } from "@/lib/recruitment";
import PageHeader, { PageBody } from "@/components/common/PageHeader";
import DataTable, {
  FilterBar,
  FilterSelect,
  Pagination,
  RowActions,
  TableCard,
} from "@/components/common/DataTable";
import ConfirmDialog from "@/components/common/ConfirmDialog";
import StageBadge from "@/components/recruitment/StageBadge";
import CandidateFormDialog from "@/components/recruitment/CandidateFormDialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

const EMPTY_FILTERS = {
  stage_status: "",
  position_id: "",
  department_id: "",
  source: "",
  applied_from: "",
  applied_to: "",
};

const DateFilter = ({ label, value, onChange, testId }) => (
  <div className="min-w-[9.5rem] space-y-1">
    <p className="text-[12px] font-medium text-muted-foreground">{label}</p>
    <Input type="date" className="h-9" value={value} onChange={(e) => onChange(e.target.value)} data-testid={testId} />
  </div>
);

const CandidatesPage = () => {
  const { can, company } = useAuth();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();

  const [rows, setRows] = useState([]);
  const [meta, setMeta] = useState({ total: 0, page: 1, limit: 20, total_pages: 1 });
  const [loading, setLoading] = useState(true);
  const [catalog, setCatalog] = useState(null);

  const [search, setSearch] = useState("");
  const [debounced, setDebounced] = useState("");
  const [filters, setFilters] = useState({
    ...EMPTY_FILTERS,
    stage_status: searchParams.get("stage_status") || "",
  });
  const [page, setPage] = useState(1);
  const [limit, setLimit] = useState(20);

  const [dialog, setDialog] = useState(null); // {mode:'create'|'edit', row}
  const [values, setValues] = useState({});
  const [errors, setErrors] = useState({});
  const [submitting, setSubmitting] = useState(false);
  const [confirm, setConfirm] = useState(null);
  const [confirmLoading, setConfirmLoading] = useState(false);

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
      const res = await api.get("/recruitment/candidates", { params });
      setRows(res.data.items || []);
      setMeta({
        total: res.data.total,
        page: res.data.page,
        limit: res.data.limit,
        total_pages: res.data.total_pages,
      });
    } catch (err) {
      toast.error(errorMessage(err, "Daftar kandidat belum dapat ditampilkan."));
      setRows([]);
    } finally {
      setLoading(false);
    }
  }, [page, limit, debounced, filters]);

  const loadCatalog = useCallback(async () => {
    try {
      const res = await api.get("/recruitment/catalog");
      setCatalog(res.data);
    } catch (err) {
      /* katalog pelengkap; daftar utama tetap tampil */
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    loadCatalog();
    document.title = "Daftar Kandidat · Rekrutmen";
  }, [loadCatalog, company?.id]);

  const openCreate = useCallback(() => {
    setValues({ source: "manual", applied_at: new Date().toISOString().slice(0, 10) });
    setErrors({});
    setDialog({ mode: "create" });
  }, []);

  // ?new=1 dari dashboard -> langsung buka form tambah
  useEffect(() => {
    if (searchParams.get("new") === "1" && can("recruitment", "create")) {
      openCreate();
      const next = new URLSearchParams(searchParams);
      next.delete("new");
      setSearchParams(next, { replace: true });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams]);

  const openEdit = (row) => {
    const v = {};
    [
      "full_name", "candidate_number", "nik", "gender", "birth_place", "birth_date", "phone", "email", "city", "address",
      "position_id", "applied_position_title", "department_id", "work_location_id", "project_id", "source", "source_detail",
      "applied_at", "expected_salary", "available_from", "last_education", "major", "institution", "graduation_year",
      "last_company", "last_position", "experience_years", "notes",
    ].forEach((k) => {
      v[k] = row[k] ?? "";
    });
    setValues(v);
    setErrors({});
    setDialog({ mode: "edit", row });
  };

  const submit = async () => {
    if (!values.full_name || values.full_name.trim().length < 2) {
      setErrors({ full_name: "Nama lengkap wajib diisi (minimal 2 karakter)." });
      return;
    }
    setSubmitting(true);
    setErrors({});
    try {
      const payload = toCandidatePayload(values);
      if (dialog.mode === "create") {
        const res = await api.post("/recruitment/candidates", payload);
        toast.success(`Kandidat "${res.data.full_name}" ditambahkan (${res.data.candidate_number}).`);
      } else {
        await api.put(`/recruitment/candidates/${dialog.row.id}`, payload);
        toast.success("Data kandidat berhasil diperbarui.");
      }
      setDialog(null);
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
      const res = await api.delete(`/recruitment/candidates/${confirm.row.id}`);
      toast.success(res.data.message);
      setConfirm(null);
      load();
    } catch (err) {
      toast.error(errorMessage(err, "Kandidat tidak dapat dihapus."));
      setConfirm(null);
    } finally {
      setConfirmLoading(false);
    }
  };

  const options = useCallback(
    (key) => (catalog?.[key] || []).map((o) => ({ value: o.id, label: o.name })),
    [catalog]
  );
  const keyOptions = useCallback(
    (key) => (catalog?.[key] || []).map((o) => ({ value: o.key, label: o.label })),
    [catalog]
  );

  const hasFilters = !!debounced || Object.values(filters).some(Boolean);

  const columns = useMemo(
    () => [
      {
        key: "full_name",
        header: "Kandidat",
        render: (row) => (
          <div className="flex min-w-0 items-start gap-2">
            <UserPlus className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
            <div className="min-w-0">
              <p className="truncate text-[13px] font-medium" data-testid={`candidate-name-${row.id}`}>
                {row.full_name}
              </p>
              <p className="truncate text-[12px] text-muted-foreground">
                {row.candidate_number}
                {row.nik ? ` · NIK ${row.nik}` : ""}
              </p>
            </div>
          </div>
        ),
      },
      {
        key: "position_name",
        header: "Posisi / Departemen",
        hideOnMobile: true,
        render: (row) => (
          <div>
            <p className="text-[13px]">{row.position_name || row.applied_position_title || "-"}</p>
            <p className="text-[12px] text-muted-foreground">{row.department_name || "-"}</p>
          </div>
        ),
      },
      {
        key: "source_label",
        header: "Sumber",
        hideOnMobile: true,
        render: (row) => <span className="text-[13px]">{row.source_label || "-"}</span>,
      },
      {
        key: "applied_at",
        header: "Tgl Masuk",
        hideOnMobile: true,
        render: (row) => <span className="text-[13px]">{row.applied_at ? formatDate(row.applied_at) : "-"}</span>,
      },
      {
        key: "stage_status",
        header: "Status",
        render: (row) => (
          <StageBadge stage={row.stage_status} label={row.stage_label} tone={row.stage_tone} testId={`candidate-stage-${row.id}`} />
        ),
      },
      {
        key: "actions",
        header: "",
        className: "w-12 text-right",
        render: (row) => (
          <RowActions
            testId={`candidate-actions-${row.id}`}
            actions={[
              { key: "detail", label: "Buka detail", icon: Eye, onSelect: () => navigate(RECRUITMENT_ROUTES.candidate(row.id)), testId: `candidate-open-${row.id}` },
              can("recruitment", "edit") && { key: "edit", label: "Ubah data", icon: Pencil, onSelect: () => openEdit(row), testId: `candidate-edit-${row.id}` },
              can("recruitment", "delete") &&
                row.can_delete && {
                  key: "delete",
                  label: "Hapus",
                  icon: Trash2,
                  destructive: true,
                  separatorBefore: true,
                  onSelect: () => setConfirm({ row }),
                  testId: `candidate-delete-${row.id}`,
                },
            ]}
          />
        ),
      },
    ],
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [can, navigate]
  );

  return (
    <>
      <PageHeader
        title="Daftar Kandidat"
        subtitle="Kandidat yang masuk lewat input HR. Klik baris untuk membuka detail, screening, dokumen, dan riwayat."
        actions={
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" onClick={() => navigate(RECRUITMENT_ROUTES.dashboard)} data-testid="candidates-back-dashboard">
              <ArrowLeft className="mr-2 h-4 w-4" /> Dashboard
            </Button>
            {can("recruitment", "create") && (
              <Button onClick={openCreate} data-testid="candidates-add-button">
                <Plus className="mr-2 h-4 w-4" /> Tambah Kandidat
              </Button>
            )}
          </div>
        }
      />
      <PageBody>
        <FilterBar
          search={search}
          onSearchChange={(v) => {
            setSearch(v);
            setPage(1);
          }}
          searchPlaceholder="Cari nama, NIK, nomor kandidat, email, atau HP…"
          showReset={hasFilters}
          activeFilterCount={Object.values(filters).filter(Boolean).length + (debounced ? 1 : 0)}
          onReset={() => {
            setSearch("");
            setFilters(EMPTY_FILTERS);
            setPage(1);
          }}
        >
          <FilterSelect
            label="Status"
            value={filters.stage_status}
            onChange={(v) => {
              setFilters((p) => ({ ...p, stage_status: v }));
              setPage(1);
            }}
            options={keyOptions("active_stages")}
            allLabel="Semua status"
            testId="filter-stage"
          />
          <FilterSelect
            label="Posisi"
            value={filters.position_id}
            onChange={(v) => {
              setFilters((p) => ({ ...p, position_id: v }));
              setPage(1);
            }}
            options={options("positions")}
            allLabel="Semua posisi"
            testId="filter-position"
          />
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
            label="Sumber"
            value={filters.source}
            onChange={(v) => {
              setFilters((p) => ({ ...p, source: v }));
              setPage(1);
            }}
            options={keyOptions("sources")}
            allLabel="Semua sumber"
            testId="filter-source"
          />
          <DateFilter
            label="Masuk dari"
            value={filters.applied_from}
            onChange={(v) => {
              setFilters((p) => ({ ...p, applied_from: v }));
              setPage(1);
            }}
            testId="filter-applied-from"
          />
          <DateFilter
            label="Sampai"
            value={filters.applied_to}
            onChange={(v) => {
              setFilters((p) => ({ ...p, applied_to: v }));
              setPage(1);
            }}
            testId="filter-applied-to"
          />
        </FilterBar>

        <TableCard>
          <DataTable
            columns={columns}
            rows={rows}
            loading={loading}
            testId="candidates-table"
            onRowClick={(row) => navigate(RECRUITMENT_ROUTES.candidate(row.id))}
            emptyProps={{
              icon: Users,
              title: hasFilters ? "Tidak ada kandidat yang cocok." : "Belum ada kandidat.",
              description: hasFilters
                ? "Coba ubah kata kunci atau hapus filter yang aktif."
                : "Tambahkan kandidat pertama. Data ini dipakai untuk screening dan tahap seleksi berikutnya.",
              actionLabel: !hasFilters && can("recruitment", "create") ? "Tambah Kandidat" : undefined,
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

      <CandidateFormDialog
        open={!!dialog}
        onOpenChange={(v) => !v && setDialog(null)}
        mode={dialog?.mode || "create"}
        catalog={catalog}
        values={values}
        errors={errors}
        onChange={(name, value) => setValues((p) => ({ ...p, [name]: value }))}
        onSubmit={submit}
        submitting={submitting}
      />

      <ConfirmDialog
        open={!!confirm}
        onOpenChange={(v) => !v && setConfirm(null)}
        title="Hapus kandidat ini?"
        description={`${confirm?.row?.full_name || "Kandidat"} akan dihapus dari daftar aktif. Riwayat dan Audit Log tetap tersimpan.`}
        destructive
        confirmLabel="Hapus"
        loading={confirmLoading}
        onConfirm={runConfirm}
      />
    </>
  );
};

export default CandidatesPage;
