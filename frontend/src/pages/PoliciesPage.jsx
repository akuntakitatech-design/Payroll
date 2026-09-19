import React, { useCallback, useEffect, useState } from "react";
import { Info, Plus, Trash2, Layers } from "lucide-react";
import { toast } from "sonner";
import { api, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import PageHeader, { PageBody } from "@/components/common/PageHeader";
import FormDialog from "@/components/common/FormDialog";
import ConfirmDialog from "@/components/common/ConfirmDialog";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { FilterSelect } from "@/components/common/DataTable";

const SCOPE_LABEL = {
  company: "Perusahaan (Default)",
  branch: "Cabang",
  division: "Divisi",
  project: "Proyek",
  employee: "Karyawan",
  system_default: "Nilai bawaan sistem",
};

const PoliciesPage = () => {
  const { can, company } = useAuth();
  const [groups, setGroups] = useState([]);
  const [overrides, setOverrides] = useState([]);
  const [loading, setLoading] = useState(true);
  const [options, setOptions] = useState({ branches: [], divisions: [], projects: [] });
  const [context, setContext] = useState({ branch_id: "", division_id: "", project_id: "" });

  const [dialogOpen, setDialogOpen] = useState(false);
  const [values, setValues] = useState({});
  const [errors, setErrors] = useState({});
  const [submitting, setSubmitting] = useState(false);
  const [confirm, setConfirm] = useState(null);
  const [confirmLoading, setConfirmLoading] = useState(false);

  const canConfig = can("policy", "config");

  const loadOptions = useCallback(async () => {
    const paths = { branches: "branches", divisions: "divisions", projects: "projects" };
    const out = {};
    await Promise.all(
      Object.entries(paths).map(async ([key, path]) => {
        try {
          const res = await api.get(`/master/${path}/options`);
          out[key] = res.data.items || [];
        } catch {
          out[key] = [];
        }
      })
    );
    setOptions(out);
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = {};
      Object.entries(context).forEach(([k, v]) => {
        if (v) params[k] = v;
      });
      const [eff, ovr] = await Promise.all([
        api.get("/policies/effective", { params }),
        api.get("/policies/overrides", { params: { limit: 200 } }),
      ]);
      setGroups(eff.data.groups || []);
      setOverrides(ovr.data.items || []);
    } catch (err) {
      toast.error(errorMessage(err, "Gagal memuat kebijakan perusahaan."));
    } finally {
      setLoading(false);
    }
  }, [context]);

  useEffect(() => {
    loadOptions();
    document.title = "Kebijakan Perusahaan · HRIS Suite";
  }, [loadOptions]);
  useEffect(() => {
    load();
  }, [load]);

  const allPolicies = groups.flatMap((g) => g.policies.map((p) => ({ ...p, group_name: g.name })));

  const openCreate = (policyKey) => {
    setValues({ config_key: policyKey || "", scope_type: "company", value: "" });
    setErrors({});
    setDialogOpen(true);
  };

  const scopeOptions = (scopeType) => {
    if (scopeType === "branch") return options.branches;
    if (scopeType === "division") return options.divisions;
    if (scopeType === "project") return options.projects;
    return [];
  };

  const submit = async () => {
    const nextErrors = {};
    if (!values.config_key) nextErrors.config_key = "Pilih kebijakan yang ingin diatur.";
    if (!values.scope_type) nextErrors.scope_type = "Pilih cakupan kebijakan.";
    if (values.scope_type !== "company" && !values.scope_id)
      nextErrors.scope_id = `Pilih ${SCOPE_LABEL[values.scope_type]?.toLowerCase() || "data"} yang menjadi cakupan aturan ini.`;
    if (values.value === "" || values.value === undefined)
      nextErrors.value = "Nilai kebijakan wajib diisi.";
    if (Object.keys(nextErrors).length) {
      setErrors(nextErrors);
      return;
    }
    const def = allPolicies.find((p) => p.key === values.config_key);
    let parsed = values.value;
    if (def?.type === "number") parsed = Number(values.value);
    if (def?.type === "boolean") parsed = values.value === "true" || values.value === true;

    setSubmitting(true);
    try {
      await api.post("/policies/overrides", {
        config_key: values.config_key,
        scope_type: values.scope_type,
        scope_id: values.scope_type === "company" ? null : values.scope_id,
        value: parsed,
        effective_from: values.effective_from || null,
        effective_to: values.effective_to || null,
        notes: values.notes || null,
      });
      toast.success("Nilai kebijakan berhasil disimpan.", {
        description: "Aturan paling spesifik akan otomatis dipakai oleh sistem.",
      });
      setDialogOpen(false);
      load();
    } catch (err) {
      setErrors({ __form__: errorMessage(err, "Nilai kebijakan tidak dapat disimpan.") });
    } finally {
      setSubmitting(false);
    }
  };

  const removeOverride = async () => {
    setConfirmLoading(true);
    try {
      const res = await api.delete(`/policies/overrides/${confirm.id}`);
      toast.success(res.data.message);
      setConfirm(null);
      load();
    } catch (err) {
      toast.error(errorMessage(err, "Nilai kebijakan tidak dapat dihapus."));
      setConfirm(null);
    } finally {
      setConfirmLoading(false);
    }
  };

  const renderValue = (policy) => {
    if (policy.type === "boolean") return policy.value ? "Ya" : "Tidak";
    return `${policy.value ?? "-"}${policy.unit ? ` ${policy.unit}` : ""}`;
  };

  const selectedPolicyDef = allPolicies.find((p) => p.key === values.config_key);

  return (
    <>
      <PageHeader
        title="Kebijakan Perusahaan"
        subtitle="Aturan perusahaan dapat diturunkan ke cabang, divisi, proyek, hingga karyawan."
        actions={
          canConfig && (
            <Button onClick={() => openCreate()} data-testid="page-header-primary-action">
              <Plus className="mr-2 h-4 w-4" /> Tambah Nilai Kebijakan
            </Button>
          )
        }
      />
      <PageBody>
        <Tabs defaultValue="effective" data-testid="policy-tabs">
          <TabsList>
            <TabsTrigger value="effective" data-testid="policy-tab-effective">
              Nilai Berlaku
            </TabsTrigger>
            <TabsTrigger value="overrides" data-testid="policy-tab-overrides">
              Daftar Override ({overrides.length})
            </TabsTrigger>
          </TabsList>

          <TabsContent value="effective" className="mt-4 space-y-4">
            <Card className="border-border bg-card p-3" data-testid="policy-scope-simulator">
              <div className="flex items-start gap-2 px-1 pb-2">
                <Layers className="mt-0.5 h-4 w-4 text-primary" />
                <div>
                  <p className="text-sm font-semibold">Simulasi cakupan</p>
                  <p className="text-xs text-muted-foreground">
                    Pilih cabang/divisi/proyek untuk melihat aturan mana yang akan dipakai sistem.
                  </p>
                </div>
              </div>
              <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap">
                <FilterSelect
                  label="Cabang"
                  value={context.branch_id}
                  onChange={(v) => setContext((p) => ({ ...p, branch_id: v }))}
                  options={options.branches.map((o) => ({ value: o.id, label: o.name }))}
                  allLabel="Tanpa cabang"
                  testId="simulator-branch"
                />
                <FilterSelect
                  label="Divisi"
                  value={context.division_id}
                  onChange={(v) => setContext((p) => ({ ...p, division_id: v }))}
                  options={options.divisions.map((o) => ({ value: o.id, label: o.name }))}
                  allLabel="Tanpa divisi"
                  testId="simulator-division"
                />
                <FilterSelect
                  label="Proyek"
                  value={context.project_id}
                  onChange={(v) => setContext((p) => ({ ...p, project_id: v }))}
                  options={options.projects.map((o) => ({ value: o.id, label: o.name }))}
                  allLabel="Tanpa proyek"
                  testId="simulator-project"
                />
              </div>
            </Card>

            {loading ? (
              <Skeleton className="h-80 w-full" />
            ) : (
              <div className="grid gap-4 xl:grid-cols-2">
                {groups.map((group) => (
                  <Card
                    key={group.key}
                    className="border-border bg-card p-4"
                    data-testid={`policy-group-${group.key}`}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <h2 className="text-section-title">{group.name}</h2>
                      <span className="shrink-0 text-[12px] text-muted-foreground">
                        {group.module_active ? "Modul aktif" : "Modul belum aktif"}
                      </span>
                    </div>
                    <ul className="mt-3 divide-y divide-border">
                      {group.policies.map((policy) => (
                        <li
                          key={policy.key}
                          className="flex flex-wrap items-center justify-between gap-2 py-2.5"
                          data-testid={`policy-row-${policy.key}`}
                        >
                          <div className="min-w-0">
                            <p className="text-[13px] font-medium">{policy.name}</p>
                            <p className="text-[12px] text-muted-foreground">
                              Sumber: {SCOPE_LABEL[policy.scope_type] || policy.source}
                            </p>
                          </div>
                          <div className="flex items-center gap-2">
                            <span
                              className="min-w-[5rem] text-right text-[14px] font-semibold text-foreground"
                              data-numeric="true"
                              data-testid={`policy-value-${policy.key}`}
                            >
                              {renderValue(policy)}
                            </span>
                            {canConfig && (
                              <Button
                                variant="ghost"
                                size="sm"
                                className="h-7 px-2 text-xs"
                                onClick={() => openCreate(policy.key)}
                                data-testid={`policy-override-${policy.key}`}
                              >
                                Atur
                              </Button>
                            )}
                          </div>
                        </li>
                      ))}
                    </ul>
                  </Card>
                ))}
              </div>
            )}
          </TabsContent>

          <TabsContent value="overrides" className="mt-4">
            <Card className="overflow-hidden border-border bg-card">
              {overrides.length === 0 ? (
                <div className="flex items-start gap-2 px-4 py-10">
                  <Info className="mt-0.5 h-4 w-4 text-muted-foreground" />
                  <div>
                    <p className="text-sm font-medium">Belum ada nilai kebijakan khusus.</p>
                    <p className="text-sm text-muted-foreground">
                      Sistem memakai nilai bawaan. Tambahkan nilai untuk perusahaan, cabang, divisi,
                      atau proyek tertentu bila aturannya berbeda.
                    </p>
                  </div>
                </div>
              ) : (
                <ul className="divide-y divide-border">
                  {overrides.map((ov) => (
                    <li
                      key={ov.id}
                      className="flex flex-wrap items-center justify-between gap-2 px-4 py-3"
                      data-testid={`override-row-${ov.id}`}
                    >
                      <div className="min-w-0">
                        <p className="text-sm font-medium">{ov.policy_name}</p>
                        <p className="text-xs text-muted-foreground">
                          {ov.group_name} · {ov.scope_label_text}
                          {ov.scope_label ? ` — ${ov.scope_label}` : ""}
                        </p>
                      </div>
                      <div className="flex items-center gap-2">
                        <span className="rounded-lg border border-border bg-background px-2.5 py-1 text-sm font-semibold">
                          {typeof ov.value === "boolean" ? (ov.value ? "Ya" : "Tidak") : String(ov.value)}
                          {ov.unit ? ` ${ov.unit}` : ""}
                        </span>
                        {can("policy", "delete") && (
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-8 w-8 text-destructive"
                            onClick={() => setConfirm(ov)}
                            data-testid={`override-delete-${ov.id}`}
                            aria-label="Hapus nilai kebijakan"
                          >
                            <Trash2 className="h-4 w-4" />
                          </Button>
                        )}
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </Card>
          </TabsContent>
        </Tabs>
      </PageBody>

      <FormDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        title="Atur Nilai Kebijakan"
        description="Nilai pada cakupan yang lebih spesifik akan mengalahkan nilai yang lebih umum."
        fields={[
          {
            name: "config_key",
            label: "Kebijakan",
            type: "select",
            required: true,
            colSpan: 2,
            options: allPolicies.map((p) => ({ value: p.key, label: `${p.group_name} — ${p.name}` })),
          },
          {
            name: "scope_type",
            label: "Cakupan",
            type: "select",
            required: true,
            options: [
              { value: "company", label: "Perusahaan (Default)" },
              { value: "branch", label: "Cabang" },
              { value: "division", label: "Divisi" },
              { value: "project", label: "Proyek" },
            ],
          },
          ...(values.scope_type && values.scope_type !== "company"
            ? [
                {
                  name: "scope_id",
                  label: SCOPE_LABEL[values.scope_type],
                  type: "select",
                  required: true,
                  options: scopeOptions(values.scope_type).map((o) => ({ value: o.id, label: o.name })),
                },
              ]
            : []),
          selectedPolicyDef?.type === "boolean"
            ? {
                name: "value",
                label: "Nilai",
                type: "select",
                required: true,
                options: [
                  { value: "true", label: "Ya" },
                  { value: "false", label: "Tidak" },
                ],
              }
            : {
                name: "value",
                label: `Nilai${selectedPolicyDef?.unit ? ` (${selectedPolicyDef.unit})` : ""}`,
                type: selectedPolicyDef?.type === "number" ? "number" : "text",
                required: true,
              },
          { name: "effective_from", label: "Berlaku Dari", type: "date" },
          { name: "effective_to", label: "Berlaku Sampai", type: "date" },
          { name: "notes", label: "Catatan", type: "textarea", colSpan: 2 },
        ]}
        values={values}
        errors={errors}
        onChange={(name, value) => {
          setValues((p) => ({
            ...p,
            [name]: value,
            ...(name === "scope_type" ? { scope_id: "" } : {}),
            ...(name === "config_key" ? { value: "" } : {}),
          }));
          setErrors((p) => ({ ...p, [name]: undefined, __form__: undefined }));
        }}
        onSubmit={submit}
        submitting={submitting}
        submitLabel="Simpan kebijakan"
      />

      <ConfirmDialog
        open={!!confirm}
        onOpenChange={(v) => !v && setConfirm(null)}
        title="Hapus nilai kebijakan ini?"
        description={`Setelah dihapus, sistem akan kembali memakai aturan yang lebih umum untuk "${confirm?.policy_name}". Riwayat perubahan tetap tercatat di audit log.`}
        destructive
        confirmLabel="Hapus nilai"
        loading={confirmLoading}
        onConfirm={removeOverride}
      />
    </>
  );
};

export default PoliciesPage;
