import React, { useCallback, useEffect, useState } from "react";
import { ArrowDown, ArrowUp, GitBranch, Loader2, Pencil, Plus, Trash2, X } from "lucide-react";
import { toast } from "sonner";
import { api, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import PageHeader, { PageBody } from "@/components/common/PageHeader";
import ConfirmDialog from "@/components/common/ConfirmDialog";
import StatusBadge, { MetaLine } from "@/components/common/StatusBadge";
import DetailDrawer from "@/components/common/DetailDrawer";
import { DetailRow } from "@/components/common/FormSection";
import DataTable, {
  FilterBar,
  FilterSelect,
  RowActions,
  TableCard,
} from "@/components/common/DataTable";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Skeleton } from "@/components/ui/skeleton";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

const emptyStep = (order) => ({
  step_order: order,
  name: "",
  approver_type: "role",
  approver_role_key: "",
  approver_user_id: null,
  approver_position_id: null,
  is_mandatory: true,
  allow_delegation: true,
  sla_days: 1,
  condition_note: "",
});

const ApprovalWorkflowPage = () => {
  const { can } = useAuth();
  const [items, setItems] = useState([]);
  const [catalog, setCatalog] = useState({ document_kinds: [], approver_types: [], scope_types: [], roles: [] });
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [kindFilter, setKindFilter] = useState("");

  const [detail, setDetail] = useState(null);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState({ code: "", name: "", document_kind: "", description: "", is_default: true });
  const [steps, setSteps] = useState([emptyStep(1)]);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [confirm, setConfirm] = useState(null);
  const [confirmLoading, setConfirmLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = { limit: 100 };
      if (search) params.q = search;
      if (kindFilter) params.document_kind = kindFilter;
      const [list, cat] = await Promise.all([
        api.get("/approval-workflows", { params }),
        api.get("/approval-workflows/catalog"),
      ]);
      setItems(list.data.items || []);
      setCatalog(cat.data);
    } catch (err) {
      toast.error(errorMessage(err, "Alur persetujuan belum dapat ditampilkan. Coba muat ulang halaman."));
    } finally {
      setLoading(false);
    }
  }, [search, kindFilter]);

  useEffect(() => {
    const t = setTimeout(load, 300);
    return () => clearTimeout(t);
  }, [load]);
  useEffect(() => {
    document.title = "Alur Persetujuan · HRIS Suite";
  }, []);

  const openCreate = () => {
    setEditing(null);
    setForm({ code: "", name: "", document_kind: catalog.document_kinds[0]?.key || "", description: "", is_default: true });
    setSteps([emptyStep(1)]);
    setError("");
    setOpen(true);
  };

  const openEdit = (wf) => {
    setEditing(wf);
    setForm({
      code: wf.code,
      name: wf.name,
      document_kind: wf.document_kind,
      description: wf.description || "",
      is_default: !!wf.is_default,
    });
    setSteps(
      (wf.steps || []).map((s, i) => ({
        ...emptyStep(i + 1),
        ...s,
        approver_role_key: s.approver_role_key || "",
        condition_note: s.condition_note || "",
        sla_days: s.sla_days ?? 1,
      }))
    );
    setError("");
    setOpen(true);
  };

  const updateStep = (index, patch) =>
    setSteps((prev) => prev.map((s, i) => (i === index ? { ...s, ...patch } : s)));

  const move = (index, dir) => {
    setSteps((prev) => {
      const next = [...prev];
      const target = index + dir;
      if (target < 0 || target >= next.length) return prev;
      [next[index], next[target]] = [next[target], next[index]];
      return next.map((s, i) => ({ ...s, step_order: i + 1 }));
    });
  };

  const removeStep = (index) =>
    setSteps((prev) => prev.filter((_, i) => i !== index).map((s, i) => ({ ...s, step_order: i + 1 })));

  const submit = async () => {
    setError("");
    if (!form.code.trim() || !form.name.trim() || !form.document_kind) {
      setError("Kode, nama, dan jenis dokumen alur persetujuan wajib diisi.");
      return;
    }
    if (!steps.length) {
      setError("Alur persetujuan harus memiliki minimal satu tahap penyetuju.");
      return;
    }
    for (const s of steps) {
      if (!s.name.trim()) {
        setError(`Tahap ke-${s.step_order} belum diberi nama. Contoh: "Persetujuan Supervisor".`);
        return;
      }
      if (s.approver_type === "role" && !s.approver_role_key) {
        setError(`Tahap "${s.name}" memakai tipe penyetuju Peran, jadi peran penyetuju wajib dipilih.`);
        return;
      }
    }
    setSubmitting(true);
    try {
      const payload = {
        ...form,
        code: form.code.toUpperCase(),
        scope_type: "company",
        scope_id: null,
        steps: steps.map((s, i) => ({
          step_order: i + 1,
          name: s.name,
          approver_type: s.approver_type,
          approver_role_key: s.approver_type === "role" ? s.approver_role_key : null,
          approver_user_id: null,
          approver_position_id: null,
          is_mandatory: !!s.is_mandatory,
          allow_delegation: !!s.allow_delegation,
          sla_days: s.sla_days === "" ? null : Number(s.sla_days),
          condition_note: s.condition_note || null,
        })),
      };
      if (editing) {
        await api.put(`/approval-workflows/${editing.id}`, payload);
        toast.success(`Alur persetujuan "${form.name}" berhasil diperbarui.`);
      } else {
        await api.post("/approval-workflows", payload);
        toast.success(`Alur persetujuan "${form.name}" berhasil dibuat.`);
      }
      setOpen(false);
      setDetail(null);
      load();
    } catch (err) {
      setError(errorMessage(err, "Alur persetujuan belum dapat disimpan. Periksa kembali data yang diisi."));
    } finally {
      setSubmitting(false);
    }
  };

  const runConfirm = async () => {
    setConfirmLoading(true);
    try {
      await api.delete(`/approval-workflows/${confirm.id}`);
      toast.success(`Alur persetujuan "${confirm.name}" berhasil dihapus.`);
      setConfirm(null);
      setDetail(null);
      load();
    } catch (err) {
      toast.error(
        errorMessage(err, "Alur ini tidak dapat dihapus karena sudah digunakan pada pengajuan lain.")
      );
      setConfirm(null);
    } finally {
      setConfirmLoading(false);
    }
  };

  const kindLabel = (key) => catalog.document_kinds.find((k) => k.key === key)?.label || key;
  const roleLabel = (key) => catalog.roles.find((r) => r.key === key)?.name || key;
  const approverText = (s) => {
    if (s.approver_type === "supervisor") return "Atasan langsung pemohon";
    if (s.approver_type === "role") return roleLabel(s.approver_role_key);
    if (s.approver_type === "user") return "Pengguna tertentu";
    if (s.approver_type === "position") return "Jabatan tertentu";
    return "-";
  };

  const columns = [
    {
      key: "name",
      header: "Alur Persetujuan",
      render: (wf) => (
        <div className="min-w-0">
          <p className="truncate text-[13px] font-medium text-foreground">{wf.name}</p>
          <MetaLine items={[wf.code, wf.is_default ? "Default" : null]} />
        </div>
      ),
    },
    {
      key: "document_kind",
      header: "Digunakan Untuk",
      hideOnMobile: true,
      render: (wf) => <span className="text-[13px]">{kindLabel(wf.document_kind)}</span>,
    },
    {
      key: "steps",
      header: "Jumlah Tahap",
      align: "right",
      hideOnMobile: true,
      render: (wf) => (
        <span data-numeric="true" className="text-[13px]">
          {(wf.steps || []).length} tahap
        </span>
      ),
    },
    {
      key: "is_default",
      header: "Default",
      hideOnMobile: true,
      render: (wf) => <span className="text-[13px]">{wf.is_default ? "Ya" : "Tidak"}</span>,
    },
    {
      key: "status",
      header: "Status",
      render: (wf) => <StatusBadge status={wf.status} />,
    },
    {
      key: "actions",
      header: "",
      align: "right",
      className: "w-12",
      render: (wf) => (
        <RowActions
          testId={`workflow-row-actions-${wf.id}`}
          actions={[
            { key: "view", label: "Lihat Detail", icon: GitBranch, onSelect: () => setDetail(wf), testId: `workflow-view-${wf.id}` },
            can("approval_workflow", "edit") && {
              key: "edit",
              label: "Ubah Alur",
              icon: Pencil,
              onSelect: () => openEdit(wf),
              testId: `workflow-edit-${wf.id}`,
            },
            can("approval_workflow", "delete") && {
              key: "delete",
              label: "Hapus Alur",
              icon: Trash2,
              destructive: true,
              separatorBefore: true,
              onSelect: () => setConfirm(wf),
              testId: `workflow-delete-${wf.id}`,
            },
          ]}
        />
      ),
    },
  ];

  const activeFilterCount = (search ? 1 : 0) + (kindFilter ? 1 : 0);

  return (
    <>
      <PageHeader
        title="Alur Persetujuan"
        subtitle="Tentukan alur dan pihak yang memberikan persetujuan untuk setiap proses."
        actions={
          can("approval_workflow", "create") && (
            <Button onClick={openCreate} data-testid="page-header-primary-action">
              <Plus className="mr-1.5 h-4 w-4" /> Buat Alur Persetujuan
            </Button>
          )
        }
      />
      <PageBody>
        <FilterBar
          search={search}
          onSearchChange={setSearch}
          searchPlaceholder="Cari kode atau nama alur…"
          showReset={activeFilterCount > 0}
          activeFilterCount={activeFilterCount}
          onReset={() => {
            setSearch("");
            setKindFilter("");
          }}
        >
          <FilterSelect
            label="Jenis Dokumen"
            value={kindFilter}
            onChange={setKindFilter}
            options={catalog.document_kinds.map((k) => ({ value: k.key, label: k.label }))}
            allLabel="Semua jenis"
            testId="filter-document-kind"
          />
        </FilterBar>

        {loading ? (
          <Skeleton className="h-64 w-full" />
        ) : (
          <TableCard>
            <DataTable
              columns={columns}
              rows={items}
              testId="workflow-table"
              onRowClick={(wf) => setDetail(wf)}
              emptyProps={{
                icon: GitBranch,
                title: "Belum ada alur persetujuan.",
                description:
                  "Buat alur pertama agar pengajuan cuti, kontrak, dan permintaan dana memiliki jalur persetujuan yang jelas.",
                actionLabel: can("approval_workflow", "create") ? "Buat Alur Persetujuan" : undefined,
                onAction: can("approval_workflow", "create") ? openCreate : undefined,
              }}
            />
          </TableCard>
        )}
      </PageBody>

      {/* Panel detail: tahap persetujuan ditampilkan berurutan */}
      <DetailDrawer
        open={!!detail}
        onOpenChange={(v) => !v && setDetail(null)}
        title={detail?.name}
        description={detail?.description || undefined}
        testId="workflow-detail-drawer"
        footer={
          <>
            {can("approval_workflow", "edit") && (
              <Button
                size="sm"
                onClick={() => {
                  const wf = detail;
                  setDetail(null);
                  openEdit(wf);
                }}
                data-testid="workflow-detail-edit"
              >
                <Pencil className="mr-1.5 h-4 w-4" /> Ubah Alur
              </Button>
            )}
            {can("approval_workflow", "delete") && (
              <Button
                size="sm"
                variant="outline"
                className="text-destructive"
                onClick={() => setConfirm(detail)}
                data-testid="workflow-detail-delete"
              >
                Hapus Alur
              </Button>
            )}
          </>
        }
      >
        {detail && (
          <div className="space-y-4">
            <div className="divide-y divide-border">
              <DetailRow label="Kode">{detail.code}</DetailRow>
              <DetailRow label="Digunakan Untuk">{kindLabel(detail.document_kind)}</DetailRow>
              <DetailRow label="Alur Default">{detail.is_default ? "Ya" : "Tidak"}</DetailRow>
              <DetailRow label="Status">
                <StatusBadge status={detail.status} />
              </DetailRow>
            </div>

            <div className="space-y-2">
              <h3 className="text-[12px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">
                Alur Persetujuan
              </h3>
              <ol className="space-y-0" data-testid="workflow-detail-steps">
                {(detail.steps || []).map((s, i) => (
                  <li key={s.id || i}>
                    <div className="flex items-start gap-3 rounded-md border border-border bg-card px-3 py-2">
                      <span
                        className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-primary-soft text-[11px] font-semibold text-primary"
                        data-numeric="true"
                      >
                        {s.step_order}
                      </span>
                      <div className="min-w-0 flex-1">
                        <p className="text-[13px] font-medium">{s.name}</p>
                        <MetaLine
                          items={[
                            approverText(s),
                            s.sla_days ? `SLA ${s.sla_days} hari` : null,
                            s.is_mandatory ? "Wajib" : "Opsional",
                          ]}
                        />
                      </div>
                    </div>
                    {i < (detail.steps || []).length - 1 && (
                      <div className="flex justify-center py-1" aria-hidden="true">
                        <ArrowDown className="h-3.5 w-3.5 text-muted-foreground" />
                      </div>
                    )}
                  </li>
                ))}
              </ol>
            </div>
          </div>
        )}
      </DetailDrawer>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-h-[92vh] overflow-y-auto sm:max-w-3xl" data-testid="workflow-dialog">
          <DialogHeader>
            <DialogTitle className="text-base font-semibold">
              {editing ? `Ubah Alur — ${editing.name}` : "Buat Alur Persetujuan"}
            </DialogTitle>
            <DialogDescription>
              Susun tahap persetujuan dari atas ke bawah. Contoh: Pemohon → Supervisor → Manager → HR.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-5">
            <section className="space-y-3">
              <div className="border-b border-border pb-1.5">
                <h3 className="text-[12px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">
                  Informasi Alur
                </h3>
              </div>
              <div className="grid grid-cols-1 gap-x-4 gap-y-3 sm:grid-cols-2">
                <div className="space-y-1.5">
                  <Label htmlFor="wf-code">
                    Kode Alur <span className="text-destructive">*</span>
                  </Label>
                  <Input
                    id="wf-code"
                    value={form.code}
                    onChange={(e) => setForm((p) => ({ ...p, code: e.target.value }))}
                    placeholder="WF-CUTI"
                    data-testid="workflow-code-input"
                  />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="wf-name">
                    Nama Alur <span className="text-destructive">*</span>
                  </Label>
                  <Input
                    id="wf-name"
                    value={form.name}
                    onChange={(e) => setForm((p) => ({ ...p, name: e.target.value }))}
                    placeholder="Persetujuan Cuti Karyawan"
                    data-testid="workflow-name-input"
                  />
                </div>
                <div className="space-y-1.5">
                  <Label>
                    Jenis Dokumen <span className="text-destructive">*</span>
                  </Label>
                  <Select
                    value={form.document_kind}
                    onValueChange={(v) => setForm((p) => ({ ...p, document_kind: v }))}
                  >
                    <SelectTrigger data-testid="workflow-kind-select">
                      <SelectValue placeholder="Pilih jenis dokumen" />
                    </SelectTrigger>
                    <SelectContent>
                      {catalog.document_kinds.map((k) => (
                        <SelectItem key={k.key} value={k.key}>
                          {k.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-1.5">
                  <Label>Jadikan alur default</Label>
                  <div className="flex h-9 items-center gap-2">
                    <Switch
                      checked={form.is_default}
                      onCheckedChange={(v) => setForm((p) => ({ ...p, is_default: v }))}
                      data-testid="workflow-default-switch"
                    />
                    <span className="text-sm text-muted-foreground">{form.is_default ? "Ya" : "Tidak"}</span>
                  </div>
                </div>
                <div className="space-y-1.5 sm:col-span-2">
                  <Label htmlFor="wf-desc">Deskripsi</Label>
                  <Input
                    id="wf-desc"
                    value={form.description}
                    onChange={(e) => setForm((p) => ({ ...p, description: e.target.value }))}
                    placeholder="Pemohon → Supervisor → Manager → HR"
                    data-testid="workflow-desc-input"
                  />
                </div>
              </div>
            </section>

            <section className="space-y-3" data-testid="approval-step-builder-list">
              <div className="flex items-center justify-between border-b border-border pb-1.5">
                <h3 className="text-[12px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">
                  Tahap Persetujuan
                </h3>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => setSteps((p) => [...p, emptyStep(p.length + 1)])}
                  data-testid="approval-step-add-button"
                >
                  <Plus className="mr-1.5 h-3.5 w-3.5" /> Tambah tahap
                </Button>
              </div>

              <div className="divide-y divide-border rounded-md border border-border">
                {steps.map((step, index) => (
                  <div key={index} className="p-3">
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-[13px] font-medium text-muted-foreground" data-numeric="true">
                        Tahap {index + 1}
                      </span>
                      <div className="flex gap-1">
                        <Button
                          type="button"
                          variant="ghost"
                          size="icon-sm"
                          disabled={index === 0}
                          onClick={() => move(index, -1)}
                          data-testid={`approval-step-move-up-${index}`}
                          aria-label="Naikkan tahap"
                        >
                          <ArrowUp className="h-3.5 w-3.5" />
                        </Button>
                        <Button
                          type="button"
                          variant="ghost"
                          size="icon-sm"
                          disabled={index === steps.length - 1}
                          onClick={() => move(index, 1)}
                          data-testid={`approval-step-move-down-${index}`}
                          aria-label="Turunkan tahap"
                        >
                          <ArrowDown className="h-3.5 w-3.5" />
                        </Button>
                        <Button
                          type="button"
                          variant="ghost"
                          size="icon-sm"
                          className="text-destructive"
                          disabled={steps.length === 1}
                          onClick={() => removeStep(index)}
                          data-testid={`approval-step-remove-button-${index}`}
                          aria-label="Hapus tahap"
                        >
                          <X className="h-3.5 w-3.5" />
                        </Button>
                      </div>
                    </div>

                    <div className="mt-2 grid grid-cols-1 gap-x-4 gap-y-3 sm:grid-cols-2">
                      <div className="space-y-1.5">
                        <Label className="text-[13px]">
                          Nama Tahap <span className="text-destructive">*</span>
                        </Label>
                        <Input
                          value={step.name}
                          onChange={(e) => updateStep(index, { name: e.target.value })}
                          placeholder="Persetujuan Supervisor"
                          data-testid={`approval-step-name-${index}`}
                        />
                      </div>
                      <div className="space-y-1.5">
                        <Label className="text-[13px]">Tipe Penyetuju</Label>
                        <Select
                          value={step.approver_type}
                          onValueChange={(v) => updateStep(index, { approver_type: v })}
                        >
                          <SelectTrigger data-testid={`approval-step-type-${index}`}>
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            {catalog.approver_types
                              .filter((t) => ["role", "supervisor"].includes(t.key))
                              .map((t) => (
                                <SelectItem key={t.key} value={t.key}>
                                  {t.label}
                                </SelectItem>
                              ))}
                          </SelectContent>
                        </Select>
                      </div>
                      {step.approver_type === "role" && (
                        <div className="space-y-1.5">
                          <Label className="text-[13px]">
                            Peran Penyetuju <span className="text-destructive">*</span>
                          </Label>
                          <Select
                            value={step.approver_role_key || ""}
                            onValueChange={(v) => updateStep(index, { approver_role_key: v })}
                          >
                            <SelectTrigger data-testid={`approval-step-role-${index}`}>
                              <SelectValue placeholder="Pilih peran" />
                            </SelectTrigger>
                            <SelectContent>
                              {catalog.roles.map((r) => (
                                <SelectItem key={r.key} value={r.key}>
                                  {r.name}
                                </SelectItem>
                              ))}
                            </SelectContent>
                          </Select>
                        </div>
                      )}
                      <div className="space-y-1.5">
                        <Label className="text-[13px]">SLA (hari)</Label>
                        <Input
                          type="number"
                          min="0"
                          value={step.sla_days ?? ""}
                          onChange={(e) => updateStep(index, { sla_days: e.target.value })}
                          data-testid={`approval-step-sla-${index}`}
                        />
                      </div>
                      <div className="flex items-center gap-5 sm:col-span-2">
                        <label className="flex items-center gap-2 text-[13px]">
                          <Switch
                            checked={!!step.is_mandatory}
                            onCheckedChange={(v) => updateStep(index, { is_mandatory: v })}
                            data-testid={`approval-step-mandatory-${index}`}
                          />
                          Wajib
                        </label>
                        <label className="flex items-center gap-2 text-[13px]">
                          <Switch
                            checked={!!step.allow_delegation}
                            onCheckedChange={(v) => updateStep(index, { allow_delegation: v })}
                            data-testid={`approval-step-delegation-${index}`}
                          />
                          Boleh didelegasikan
                        </label>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </section>

            {error && (
              <div
                className="rounded-md border border-danger-border bg-danger-soft px-3 py-2 text-[13px] text-danger"
                data-testid="workflow-error"
              >
                {error}
              </div>
            )}
          </div>

          <DialogFooter className="gap-2">
            <Button variant="outline" onClick={() => setOpen(false)} disabled={submitting}>
              Batal
            </Button>
            <Button onClick={submit} disabled={submitting} data-testid="workflow-submit">
              {submitting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              {editing ? "Simpan perubahan" : "Simpan alur"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={!!confirm}
        onOpenChange={(v) => !v && setConfirm(null)}
        title="Hapus alur persetujuan?"
        description={`Alur "${confirm?.name}" beserta seluruh tahapnya akan dihapus. Pengajuan baru untuk jenis dokumen ini tidak akan punya jalur persetujuan sampai Anda membuat alur pengganti.`}
        destructive
        confirmLabel="Hapus alur"
        loading={confirmLoading}
        onConfirm={runConfirm}
      />
    </>
  );
};

export default ApprovalWorkflowPage;
